from collections import defaultdict
import logging
import time
from datetime import UTC, datetime, timedelta
from pydantic import BaseModel, computed_field
from zoneinfo import ZoneInfo

from app.arr.base import (
    COMMAND_TIMEOUT,
    ArrClient,
    CommandStatus,
    QualityProfileModel,
    SearchCheck,
    SearchResult,
)
from app.settings import settings


logger = logging.getLogger(__name__)


class EpisodeFileModel(BaseModel):
    customFormatScore: int
    id: int


class EpisodeDetailModel(BaseModel):
    seriesId: int
    episodeId: int
    seasonNumber: int


class EpisodeReleaseModel(BaseModel):
    customFormatScore: int
    approved: bool
    fullSeason: bool
    rejections: list[str]
    guid: str
    indexerId: int
    title: str


class EpisodeModel(BaseModel):
    client: "SonarrClient"
    tvdbId: int
    seriesId: int
    seasonNumber: int
    episodeNumber: int
    episodeFileId: int
    hasFile: bool
    monitored: bool
    airDateUtc: datetime | None = None
    lastSearchTime: datetime | None = None
    title: str
    id: int

    def _is_released(self):
        return datetime.now(tz=UTC) >= self.airDateUtc if self.airDateUtc else False

    def _is_recently_searched(self):
        return (
            bool(self.lastSearchTime)
            and datetime.now(tz=UTC)
            - timedelta(minutes=settings.search_refresh_interval)
            < self.lastSearchTime
        )

    def _can_be_upgraded(self, series: "SeriesModel"):
        custom_format_score = self.client.get_episode_custom_format_score(
            series_id=self.seriesId, episode_file_id=self.episodeFileId
        )
        if not custom_format_score:
            return False
        profile_max_custom_score = self.client.get_quality_profile_custom_format_score(
            quality_profile_id=series.qualityProfileId
        )
        if not profile_max_custom_score:
            return False
        logger.debug(
            "\n".join(
                [
                    str(self),
                    f"Custom Format Score: {custom_format_score}, Profile Max Score: {profile_max_custom_score}",
                ]
            )
        )
        return custom_format_score < profile_max_custom_score

    def _get_local_last_search_time(self):
        return (
            self.lastSearchTime.astimezone(tz=ZoneInfo("localtime"))
            if self.lastSearchTime
            else ""
        )

    def can_be_searched(self, series: "SeriesModel"):
        if not self.monitored:
            return SearchCheck(reason="Unmonitored", should_search=False)
        elif not self._is_released():
            return SearchCheck(reason="Unreleased", should_search=False)
        elif self._is_recently_searched():
            return SearchCheck(
                reason=f"Recently Searched at {self._get_local_last_search_time()}",
                should_search=False,
            )
        elif not self.hasFile:
            return SearchCheck(reason="Has no file", should_search=True)
        elif self._can_be_upgraded(series=series):
            return SearchCheck(reason="Can be upgraded", should_search=True)
        return SearchCheck(reason="Can't be upgraded", should_search=False)

    def __str__(self):
        return self.title


class SeasonModel(BaseModel):
    client: "SonarrClient"
    series: "SeriesModel"
    seasonNumber: int
    episodes: list[EpisodeModel]
    media_type = "season"

    def can_be_searched(self):
        for episode in self.episodes:
            check = episode.can_be_searched(series=self.series)
            if check.should_search:
                return SearchCheck(
                    reason=f"Due to episode {episode}. Reason: {check.reason}",
                    should_search=True,
                )
        return SearchCheck(reason="No episodes can be searched", should_search=False)

    def is_qualified_release(self, release: EpisodeReleaseModel):
        lowest_score_episode = min(
            [
                self.client.get_episode_custom_format_score(
                    series_id=self.series.id, episode_file_id=e.episodeFileId
                )
                or 0
                for e in self.episodes
            ]
        )
        if release.approved:
            return True
        return (
            release.customFormatScore > lowest_score_episode
            and len(release.rejections) == 1
            and release.rejections[0].startswith(
                "Existing file on disk has a equal or higher Custom Format score"
            )
            and release.fullSeason
        )

    def _search_by_command(self):
        command = self.client.search_season(
            series_id=self.series.id, season_number=self.seasonNumber
        )
        logger.debug(f"Triggering search for season: {self}")
        try:
            result = self.client.wait_for_command(command_id=command.id)
        except Exception:
            return SearchResult(
                message=f"Timed out waiting for command {command.id} for season: {self}",
                success=False,
            )
        return SearchResult(
            message="\n".join(
                [f"Triggered search for season: {self}", f"Result: {result}"]
            ),
            success=True,
        )

    def _search_by_release(self):
        logger.debug(f"Grabbing releases for season: {self}")
        try:
            releases = self.client.get_releases(
                series_id=self.series.id,
                season_number=self.seasonNumber,
            )
        except Exception:
            logger.error(f"Failed to get releases for season: {self}", exc_info=True)
            return SearchResult(
                message=f"Attempted to grab releases for season {self} but failed",
                success=False,
            )
        qualified_release = next(
            (r for r in releases if self.is_qualified_release(release=r)),
            None,
        )
        if not qualified_release:
            return SearchResult(
                message=f"No qualified release found for season: {self}",
                success=True,
            )
        try:
            self.client.grab_release(
                guid=qualified_release.guid,
                indexerId=qualified_release.indexerId,
            )
        except Exception:
            return SearchResult(
                message="\n".join(
                    [
                        f"Failed to grab release for season: {self}",
                        f"Release name: {qualified_release.title}",
                    ]
                ),
                success=False,
            )
        return SearchResult(
            message="\n".join(
                [
                    f"Grabbed release for season: {self}",
                    f"Release Name: {qualified_release.title}",
                ]
            ),
            success=True,
        )

    def search(self):
        if settings.sonarr_search == "command":
            return self._search_by_command()
        return self._search_by_release()

    def __str__(self) -> str:
        return f"{self.series.title} S{self.seasonNumber:2}"


class SeriesModel(BaseModel):
    client: "SonarrClient"
    title: str
    monitored: bool
    qualityProfileId: int
    id: int

    @computed_field
    @property
    def seasons(self):
        episodes = self.client.get_all_episodes(series_id=self.id)
        season_map = defaultdict[int, list[EpisodeModel]]()
        for e in episodes:
            season_map[e.seasonNumber].append(e)
        return [
            SeasonModel(episodes=e, seasonNumber=s, series=self, client=self.client)
            for s, e in season_map.items()
        ]


class SonarrClient(ArrClient):
    @classmethod
    def initialize(cls, *args, **kwargs):
        return super().initialize(
            url=str(settings.sonarr_url) if settings.sonarr_url else None,
            api_key=settings.sonarr_api_key,
        )

    def get_quality_profile_custom_format_score(self, quality_profile_id: int):
        response = self.get("/api/v3/qualityprofile")
        quality_profiles = [
            QualityProfileModel.model_validate(_) for _ in response.json()
        ]
        return next(
            (
                quality_profile.cutoffFormatScore
                for quality_profile in quality_profiles
                if quality_profile.id == quality_profile_id
            ),
            None,
        )

    def get_episode_files(self, series_id: int):
        response = self.get(
            "/api/v3/episodeFile",
            params={"seriesId": series_id},
        )
        return [EpisodeFileModel.model_validate(_) for _ in response.json()]

    def get_episode_custom_format_score(self, series_id: int, episode_file_id: int):
        episode_files = self.get_episode_files(series_id=series_id)
        return next(
            (ef.customFormatScore for ef in episode_files if ef.id == episode_file_id),
            None,
        )

    def get_all_series(self):
        response = self.get("/api/v3/series")
        return [
            SeriesModel.model_validate({**_, "client": self}) for _ in response.json()
        ]

    def get_all_episodes(self, series_id: int):
        response = self.get("/api/v3/episode", params={"seriesId": series_id})
        return [
            EpisodeModel.model_validate({**_, "client": self}) for _ in response.json()
        ]

    def search_season(self, series_id: int, season_number: int):
        response = self.post(
            "/api/v3/command",
            json={
                "name": "SeasonSearch",
                "seasonNumber": season_number,
                "seriesId": series_id,
            },
        )
        return CommandStatus.model_validate(response.json())

    def search_episodes(self, episode_ids: list[int]):
        response = self.post(
            "/api/v3/command", json={"name": "EpisodeSearch", "episodeIds": episode_ids}
        )
        return CommandStatus.model_validate(response.json())

    def get_command_status(self, id: int):
        response = self.get(f"/api/v3/command/{id}")
        return CommandStatus.model_validate(response.json())

    def wait_for_command(self, command_id: int):
        start_time = datetime.now()
        while datetime.now() - start_time < timedelta(minutes=COMMAND_TIMEOUT):
            command_status = self.get_command_status(id=command_id)
            if command_status.status == "completed":
                return command_status.message
            time.sleep(10)
        return "Timed out waiting for command"

    def get_releases(self, series_id: int, season_number: int):
        response = self.get(
            "/api/v3/release",
            params={"seriesId": series_id, "seasonNumber": season_number},
        )
        return [EpisodeReleaseModel.model_validate(_) for _ in response.json()]

    def grab_release(self, guid: str, indexerId: int):
        self.post("/api/v3/release", json={"guid": guid, "indexerId": indexerId})
