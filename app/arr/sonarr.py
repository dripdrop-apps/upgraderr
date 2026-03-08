from datetime import UTC, datetime, timedelta
import time
import cachetools
from pydantic import BaseModel

from app.arr.base import COMMAND_TIMEOUT, ArrClient, CommandStatus, QualityProfileModel
from app.settings import settings


class EpisodeModel(BaseModel):
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

    def is_released(self):
        return datetime.now(tz=UTC) >= self.airDateUtc if self.airDateUtc else False


class SeriesModel(BaseModel):
    title: str
    monitored: bool
    qualityProfileId: int
    id: int
    episodes: list[EpisodeModel] = []


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

    @cachetools.cachedmethod(cache=lambda self: self.cache)
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
        return [SeriesModel.model_validate(_) for _ in response.json()]

    def get_all_episodes(self, series_id: int):
        response = self.get("/api/v3/episode", params={"seriesId": series_id})
        return [EpisodeModel.model_validate(_) for _ in response.json()]

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
