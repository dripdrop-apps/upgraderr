import argparse
import logging
import logging.handlers
import random
import sys
from apscheduler.executors.pool import ThreadPoolExecutor
from apscheduler.jobstores.sqlalchemy import SQLAlchemyJobStore
from apscheduler.schedulers.blocking import BlockingScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.date import DateTrigger
from datetime import timedelta, datetime
from sqlalchemy import select, or_, update
from sqlalchemy.orm import Session
from typing import NamedTuple
from app import arr_client
from app.db import Movie, Episode, get_db_session, engine
from app.notifications import send_search_notification, send_sync_notification
from app.settings import settings

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s -  %(levelname)s - %(message)s",
    handlers=[
        logging.handlers.RotatingFileHandler(
            filename=f"{settings.logs_directory}/upgraderr.log",
            maxBytes=10 * 1024 * 1024,
            backupCount=5,
        ),
        logging.StreamHandler(sys.stdout),
    ],
)

logger = logging.getLogger("upgraderr")
logger.setLevel(level=settings.log_level)


def log_and_notify_sync(message: str):
    logger.info(message)
    send_sync_notification(body=message)


def log_and_notify_search(message: str):
    logger.info(message)
    send_search_notification(body=message)


scheduler = BlockingScheduler()
scheduler.configure(
    jobstores={"default": SQLAlchemyJobStore(engine=engine)},
    executers={"default": ThreadPoolExecutor(max_workers=1)},
    job_defaults={"coalesce": True},
)


class MovieSearch(NamedTuple):
    movie_id: int
    movie_title: str

    def __str__(self):
        return f"Movie: {self.movie_title}"


class SeasonSearch(NamedTuple):
    series_id: int
    series_title: str
    season_number: int

    def __str__(self) -> str:
        return f"Series: {self.series_title} S{self.season_number:02}"


class Upgraderr:
    def __init__(self):
        self.sonarr = arr_client.SonarrClient.initialize()
        self.radarr = arr_client.RadarrClient.initialize()
        self.dry_run = settings.dry_run
        if self.dry_run:
            logger.info("DRY RUN: No searches will be executed.")

    def _can_movie_be_searched(self, movie: arr_client.MovieModel):
        if not self.radarr:
            logger.info("Radarr is not configured. Skipping...")
            return False
        elif not movie.monitored:
            logger.debug(f"Skipping unmonitored movie ({movie.title})")
            return False

        movie_custom_format_score = self.radarr.get_movie_custom_format_score(
            movie_id=movie.id
        )
        profile_max_custom_score = self.radarr.get_quality_profile_custom_format_score(
            quality_profile_id=movie.qualityProfileId
        )

        movie_can_be_upgraded = (
            movie.hasFile
            and isinstance(movie_custom_format_score, int)
            and isinstance(profile_max_custom_score, int)
            and movie_custom_format_score < profile_max_custom_score
        )
        if movie_can_be_upgraded:
            logger.debug(f"Movie ({movie.title}) can be upgraded.")
            logger.debug(
                f"Current score: {movie_custom_format_score}, Max score: {profile_max_custom_score}"
            )
        if not movie.hasFile:
            logger.debug(f"Movie ({movie.title}) does not have a file.")
        return movie_can_be_upgraded or not movie.hasFile

    def sync_movies(self, session: Session):
        if not self.radarr:
            logger.debug("Radarr is not configured. Skipping...")
            return

        logger.info("Syncing movies from radarr...")
        movies = self.radarr.get_all_movies()
        for movie in movies:
            obj = Movie(
                tmdb_id=movie.tmdbId,
                movie_id=movie.id,
                last_searched=movie.lastSearchTime,
            )
            session.merge(obj)
            session.commit()
        log_and_notify_sync(message=f"Successfully synced {len(movies)} movies.")

    def _can_episode_be_searched(
        self, series: arr_client.SeriesModel, episode: arr_client.EpisodeModel
    ):
        if not self.sonarr:
            return False
        elif not episode.monitored:
            logger.debug(
                f"Skipping unmonitored episode ({series.title} - {episode.title})"
            )
            return False

        episode_custom_format_score = self.sonarr.get_episode_custom_format_score(
            episode_id=episode.id, series_id=episode.seriesId
        )
        profile_max_custom_format_score = (
            self.sonarr.get_quality_profile_custom_format_score(
                quality_profile_id=series.qualityProfileId,
            )
        )
        episode_can_be_upgraded = (
            episode.hasFile
            and isinstance(episode_custom_format_score, int)
            and isinstance(profile_max_custom_format_score, int)
            and episode_custom_format_score < profile_max_custom_format_score
        )
        if episode_can_be_upgraded:
            logger.debug(f"Episode ({series.title} - {episode.title}) can be upgraded.")
            logger.debug(
                f"Current Score {episode_custom_format_score}, Max Score {profile_max_custom_format_score}"
            )
        if not episode.hasFile:
            logger.debug(f"Episode ({series.title} - {episode.title}) has no file.")
        return episode_can_be_upgraded or not episode.hasFile

    def sync_episodes(self, session: Session):
        if not self.sonarr:
            logger.debug("Sonarr is not configured. Skipping...")
            return

        logger.info("Syncing episodes from sonarr...")
        count = 0
        all_series = self.sonarr.get_all_series()
        for series in all_series:
            series_id = series.id
            episodes = self.sonarr.get_all_episodes(series_id=series_id)
            for episode in episodes:
                obj = Episode(
                    tvdb_id=episode.tvdbId,
                    episode_id=episode.id,
                    episode_number=episode.episodeNumber,
                    season_number=episode.seasonNumber,
                    series_id=series_id,
                    last_searched=episode.lastSearchTime,
                )
                session.merge(obj)
                session.commit()
                count += 1
        log_and_notify_sync(
            message=f"Successfully synced {count} episodes from {len(all_series)} series."
        )

    @classmethod
    def sync(cls):
        upgraderr = cls()
        log_and_notify_sync(message="Starting media sync")
        with get_db_session() as session:
            upgraderr.sync_movies(session=session)
            upgraderr.sync_episodes(session=session)
        logger.info("Media sync completed.")
        log_and_notify_sync(message="Media sync completed")

    def search_movie(self, movie_ids: list[int], session: Session):
        if not self.radarr:
            return

        self.radarr.search_movie(movie_ids=movie_ids)
        query = (
            update(Movie)
            .where(Movie.movie_id.in_(movie_ids))
            .values(last_searched=datetime.now())
        )
        session.execute(query)
        session.commit()

    def get_movie_searches(self, session: Session):
        movies_to_search = set[MovieSearch]()

        if not self.radarr:
            logger.debug("Radarr is not configured. Skipping...")
            return list(movies_to_search)

        query = (
            select(Movie)
            .where(
                Movie.job_id.is_(None),
                or_(
                    Movie.last_searched
                    < (datetime.now() - timedelta(minutes=settings.search_state_reset)),
                    Movie.last_searched.is_(None),
                ),
            )
            .order_by(Movie.tmdb_id.asc())
        )
        movies = session.scalars(query).all()
        for movie in movies:
            all_movies = self.radarr.get_all_movies()
            matching_movie = next(
                (m for m in all_movies if m.tmdbId == movie.tmdb_id), None
            )
            if matching_movie and self._can_movie_be_searched(matching_movie):
                movies_to_search.add(
                    MovieSearch(
                        movie_id=matching_movie.id, movie_title=matching_movie.title
                    )
                )
        return list(movies_to_search)

    def search_season(self, series_id: int, season_number: int, session: Session):
        if not self.sonarr:
            return

        self.sonarr.search_season(series_id=series_id, season_number=season_number)
        query = (
            update(Episode)
            .where(
                Episode.series_id == series_id, Episode.season_number == season_number
            )
            .values(last_searched=datetime.now())
        )
        session.execute(query)
        session.commit()

    def get_season_searches(self, session: Session):
        seasons_to_search = set[SeasonSearch]()

        if not self.sonarr:
            logger.debug("Sonarr is not configured. Skipping...")
            return list(seasons_to_search)

        query = (
            select(Episode)
            .where(
                Episode.job_id.is_(None),
                or_(
                    Episode.last_searched
                    < (datetime.now() - timedelta(hours=settings.search_state_reset)),
                    Episode.last_searched.is_(None),
                ),
            )
            .order_by(Episode.tvdb_id.asc())
        )
        episodes = session.scalars(query).all()
        for episode in episodes:
            all_series = self.sonarr.get_all_series()
            matching_series = next((s for s in all_series if s.id == episode.series_id))
            if matching_series:
                all_episodes = self.sonarr.get_all_episodes(series_id=episode.series_id)
                matching_episode = next(
                    (e for e in all_episodes if e.tvdbId == episode.tvdb_id), None
                )
                if matching_episode and self._can_episode_be_searched(
                    series=matching_series, episode=matching_episode
                ):
                    seasons_to_search.add(
                        SeasonSearch(
                            series_id=matching_series.id,
                            series_title=matching_series.title,
                            season_number=episode.season_number,
                        )
                    )
        return list(seasons_to_search)

    @classmethod
    def search(cls):
        upgraderr = cls()
        log_and_notify_search(message="Starting media search")

        searches = list[MovieSearch | SeasonSearch]()
        searches_triggered = 0

        with get_db_session() as session:
            movies_to_search = upgraderr.get_movie_searches(session=session)
            searches.extend(movies_to_search)
            seasons_to_search = upgraderr.get_season_searches(session=session)
            searches.extend(seasons_to_search)
            random.shuffle(searches)
            for media_search in searches[: settings.max_search_limit]:
                if upgraderr.dry_run:
                    logger.info(f"DRY RUN: Skipping searching for {media_search}")
                elif isinstance(media_search, MovieSearch) and upgraderr.radarr:
                    upgraderr.search_movie(
                        movie_ids=[media_search.movie_id], session=session
                    )
                    log_and_notify_search(
                        message=f"Triggering search for {media_search}"
                    )
                elif isinstance(media_search, SeasonSearch) and upgraderr.sonarr:
                    upgraderr.search_season(
                        series_id=media_search.series_id,
                        season_number=media_search.season_number,
                        session=session,
                    )
                    log_and_notify_search(
                        message=f"Triggering search for {media_search}"
                    )
                searches_triggered += 1
        log_and_notify_search(
            message=f"Media searching completed. Queued {searches_triggered} searches."
        )

    @classmethod
    def search_task(cls):
        upgraderr = cls()
        upgraderr.search()
        scheduler.add_job(
            Upgraderr.search_task,
            trigger=DateTrigger(
                run_date=datetime.now() + timedelta(minutes=settings.search_interval)
            ),
            id="search",
            replace_existing=True,
        )

    @classmethod
    def run(cls):
        if settings.one_shot:
            upgraderr = cls()
            upgraderr.sync()
            upgraderr.search()
            return

        scheduler.add_job(
            func=Upgraderr.sync,
            trigger=CronTrigger(hour=0, minute=0),
            id="sync-cron",
            replace_existing=True,
        )

        logger.info("Running immediate sync...")
        scheduler.add_job(func=Upgraderr.sync)
        scheduler.add_job(
            func=Upgraderr.search_task, id="search", replace_existing=True
        )
        scheduler.start()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(prog="upgraderr")

    parser.add_argument(
        "action",
        choices=["sync", "search", "run", "clear"],
        help="""
        Sync the database with the Sonarr/Radarr instances.
        Search for new episodes/seasons.
        Run scheduler.
        Clear jobs from the scheduler.
        """,
    )

    args = parser.parse_args()

    if args.action == "sync":
        Upgraderr.sync()
    elif args.action == "search":
        Upgraderr.search()
    elif args.action == "run":
        Upgraderr.run()
    elif args.action == "clear":
        scheduler.remove_all_jobs()
