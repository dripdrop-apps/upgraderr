import logging
from upgraderr import arr_client, db

logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)


class Upgraderr:
    def __init__(self):
        self.sonarr = arr_client.SonarrClient.initialize()
        self.radarr = arr_client.RadarrClient.initialize()

    def _get_movie_search_reason(self, movie: arr_client.MovieModel):
        if not self.radarr:
            return None

        movie_custom_format_score = self.radarr.get_movie_custom_format_score(
            movie_id=movie.id
        )
        profile_max_custom_score = self.radarr.get_quality_profile_custom_format_score(
            quality_profile_id=movie.qualityProfileId
        )
        movie_can_be_upgraded = (
            movie.monitored
            and isinstance(movie_custom_format_score, int)
            and isinstance(profile_max_custom_score, int)
            and movie_custom_format_score < profile_max_custom_score
        )
        if movie_can_be_upgraded:
            return "Can be upgraded"
        if not movie.hasFile:
            return "Missing file"
        return None

    def _sync_movies(self):
        if not self.radarr:
            logging.info("Radarr is not configured. Skipping...")
            return

        with db.get_session() as session:
            movies = self.radarr.get_all_movies()
            for movie in movies:
                obj = db.Movie(
                    id=movie.id,
                    search_reason=self._get_movie_search_reason(movie=movie),
                    last_searched=movie.lastSearchTime,
                )
                session.merge(obj)
                session.commit()

    def _get_episode_search_reason(
        self, series: arr_client.SeriesModel, episode: arr_client.EpisodeModel
    ):
        if not self.sonarr:
            return

        episode_custom_format_score = self.sonarr.get_episode_custom_format_score(
            episode_id=episode.id, series_id=episode.seriesId
        )
        profile_max_custom_format_score = (
            self.sonarr.get_quality_profile_custom_format_score(
                quality_profile_id=series.qualityProfileId,
            )
        )
        episode_can_be_upgraded = (
            episode.monitored
            and isinstance(episode_custom_format_score, int)
            and isinstance(profile_max_custom_format_score, int)
            and episode_custom_format_score < profile_max_custom_format_score
        )
        if episode_can_be_upgraded:
            return "Can be upgraded"
        if not episode.hasFile:
            return "Missing file"
        return None

    def _sync_episodes(self):
        if not self.sonarr:
            logger.info("Sonarr is not configured. Skipping...")
            return

        with db.get_session() as session:
            all_series = self.sonarr.get_all_series()
            for series in all_series:
                series_id = series.id
                episodes = self.sonarr.get_all_episodes(series_id=series_id)
                for episode in episodes:
                    obj = db.Episode(
                        episode_number=episode.episodeNumber,
                        season_number=episode.seasonNumber,
                        series_id=series_id,
                        search_reason=self._get_episode_search_reason(
                            series=series, episode=episode
                        ),
                        last_searched=episode.lastSearchTime,
                    )
                    session.merge(obj)
                    session.commit()

    def sync(self):
        logger.info("Starting media sync...")
        self._sync_movies()
        self._sync_episodes()
        logger.info("Media sync completed.")

    def upgrade(self):
        pass
