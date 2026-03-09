import logging
import time
from datetime import UTC, datetime, timedelta
from pydantic import BaseModel, ConfigDict

from app.arr.base import (
    ArrClient,
    CommandStatus,
    QualityProfileModel,
    COMMAND_TIMEOUT,
    SearchCheck,
    SearchResult,
)
from app.settings import settings

logger = logging.getLogger(__name__)


class MovieModel(BaseModel):
    model_config = ConfigDict(arbitrary_types_allowed=True)

    client: "RadarrClient"
    tmdbId: int
    qualityProfileId: int
    hasFile: bool
    monitored: bool
    releaseDate: datetime | None = None
    lastSearchTime: datetime | None = None
    title: str
    id: int

    def _is_released(self):
        return datetime.now(tz=UTC) >= self.releaseDate if self.releaseDate else False

    def _is_recently_searched(self):
        return (
            bool(self.lastSearchTime)
            and datetime.now(tz=UTC)
            - timedelta(minutes=settings.search_refresh_interval)
            < self.lastSearchTime
        )

    def _can_be_upgraded(self):
        custom_format_score = self.client.get_movie_custom_format_score(
            movie_id=self.id
        )
        if not custom_format_score:
            return False
        profile_max_custom_score = self.client.get_quality_profile_custom_format_score(
            quality_profile_id=self.qualityProfileId
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
        return self.lastSearchTime.astimezone() if self.lastSearchTime else ""

    def can_be_searched(self):
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
        elif self._can_be_upgraded():
            return SearchCheck(reason="Can be upgraded", should_search=True)
        return SearchCheck(reason="Can't be upgraded", should_search=False)

    def search(self):
        command = self.client.search_movie(movie_ids=[self.id])
        logger.debug(f"Trigger search for movie: {self}")
        try:
            result = self.client.wait_for_command(command_id=command.id)
        except Exception:
            return SearchResult(
                message=f"Timed out waiting for command {command.id} for movie: {self}",
                success=False,
            )
        return SearchResult(
            message="\n".join(
                [f"Triggered search for movie: {self}", f"Result: {result}"]
            ),
            success=True,
        )

    def __str__(self):
        return self.title


class MovieFileModel(BaseModel):
    customFormatScore: int
    id: int


class RadarrClient(ArrClient):
    @classmethod
    def initialize(cls, *args, **kwargs):
        return super().initialize(
            url=str(settings.radarr_url) if settings.radarr_url else None,
            api_key=settings.radarr_api_key,
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

    def get_movie_custom_format_score(self, movie_id: int):
        response = self.get("/api/v3/movieFile", params={"movieId": movie_id})
        movie_files = [MovieFileModel.model_validate(_) for _ in response.json()]
        return max(
            (movie_file.customFormatScore for movie_file in movie_files), default=None
        )

    def get_all_movies(self):
        response = self.get("/api/v3/movie")
        return [
            MovieModel.model_validate({**_, "client": self}) for _ in response.json()
        ]

    def search_movie(self, movie_ids: list[int]):
        response = self.post(
            "/api/v3/command", json={"name": "MoviesSearch", "movieIds": movie_ids}
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
