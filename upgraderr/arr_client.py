import requests
from datetime import datetime
from functools import lru_cache
from pydantic import BaseModel
from upgraderr.settings import settings
from typing import TypeVar, Generic

T = TypeVar("T")


class ArrClient(Generic[T], requests.Session):
    def __init__(self, url: str, api_key: str | None = None):
        super().__init__()
        self.base_url = url
        if api_key:
            self.headers.update({"X-Api-Key": api_key})

    def request(self, method: str, url: str, *args, **kwargs):
        response = super().request(method, f"{self.base_url}/{url}", *args, **kwargs)
        response.raise_for_status()
        return response

    @classmethod
    def initialize(cls, url: str | None = None, api_key: str | None = None):
        if url:
            return cls(url=url, api_key=api_key)
        return None


class QualityProfileModel(BaseModel):
    cutoffFormatScore: int
    id: int


class SeriesModel(BaseModel):
    title: str
    monitored: bool
    qualityProfileId: int
    id: int


class EpisodeModel(BaseModel):
    tvdbId: int
    seriesId: int
    seasonNumber: int
    episodeNumber: int
    hasFile: bool
    monitored: bool
    lastSearchTime: datetime | None = None
    title: str
    id: int


class EpisodeFileModel(BaseModel):
    customFormatScore: int
    id: int


class SonarrClient(ArrClient):
    @classmethod
    def initialize(cls, *args, **kwargs):
        return super().initialize(
            url=settings.sonarr_url.unicode_string() if settings.sonarr_url else None,
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

    @lru_cache()
    def get_episode_files(self, series_id: str):
        response = self.get(
            "/api/v3/episodeFile",
            params={"seriesId": series_id},
        )
        return [EpisodeFileModel.model_validate(_) for _ in response.json()]

    def get_episode_custom_format_score(self, series_id: int, episode_id: int):
        episode_files = self.get_episode_files(series_id=series_id)
        return next(
            (ef.customFormatScore for ef in episode_files if ef.id == episode_id), None
        )

    @lru_cache()
    def get_all_series(self):
        response = self.get("/api/v3/series")
        return [SeriesModel.model_validate(_) for _ in response.json()]

    @lru_cache()
    def get_all_episodes(self, series_id: int):
        response = self.get("/api/v3/episode", params={"seriesId": series_id})
        return [EpisodeModel.model_validate(_) for _ in response.json()]

    def search_season(self, series_id: int, seasonNumber: int):
        self.get(
            "/api/v3/command",
            data={
                "name": "SeasonSearch",
                "seasonNumber": seasonNumber,
                "seriesId": series_id,
            },
        )

    def search_episodes(self, episode_ids: list[int]):
        self.get(
            "/api/v3/command", data={"name": "EpisodeSearch", "episodeIds": episode_ids}
        )


class MovieModel(BaseModel):
    tmdbId: int
    qualityProfileId: int
    hasFile: bool
    monitored: bool
    lastSearchTime: datetime | None = None
    title: str
    id: int


class MovieFileModel(BaseModel):
    customFormatScore: int
    id: int


class RadarrClient(ArrClient):
    @classmethod
    def initialize(cls, *args, **kwargs):
        return super().initialize(
            url=settings.radarr_url.unicode_string() if settings.radarr_url else None,
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
        return next(
            (
                movie_file.customFormatScore
                for movie_file in movie_files
                if movie_file.id == movie_id
            ),
            None,
        )

    @lru_cache()
    def get_all_movies(self):
        response = self.get("/api/v3/movie")
        return [MovieModel.model_validate(_) for _ in response.json()]

    def search_movie(self, movie_ids: list[int]):
        self.post(
            "/api/v3/command", data={"name": "MoviesSearch", "movieIds": movie_ids}
        )
