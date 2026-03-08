import time
from datetime import UTC, datetime, timedelta
from pydantic import BaseModel

from app.arr.base import ArrClient, CommandStatus, QualityProfileModel, COMMAND_TIMEOUT
from app.settings import settings


class MovieModel(BaseModel):
    tmdbId: int
    qualityProfileId: int
    hasFile: bool
    monitored: bool
    releaseDate: datetime | None = None
    lastSearchTime: datetime | None = None
    title: str
    id: int

    def is_released(self):
        return datetime.now(tz=UTC) >= self.releaseDate if self.releaseDate else False


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
        return [MovieModel.model_validate(_) for _ in response.json()]

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
