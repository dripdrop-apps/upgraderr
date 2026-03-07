import argparse
import logging
import logging.handlers
import random
import sys
import time
from apscheduler.executors.pool import ThreadPoolExecutor
from apscheduler.jobstores.sqlalchemy import SQLAlchemyJobStore
from apscheduler.schedulers.blocking import BlockingScheduler
from apscheduler.triggers.date import DateTrigger
from datetime import timedelta, datetime
from typing import NamedTuple
from app import arr_client
from app.db import engine
from app.notifications import send_search_notification
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

    def get_movies(self):
        if not self.radarr:
            logger.debug("Radarr is not configured. Skipping...")
            return []

        logger.debug("Retrieving movies from radarr...")
        movies = self.radarr.get_all_movies()
        logger.info(f"Successfully retrieved {len(movies)} movies.")
        return movies

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

    def get_all_series(self):
        if not self.sonarr:
            logger.debug("Sonarr is not configured. Skipping...")
            return []
        logger.debug("Retrieving episodes from sonarr...")
        all_series = self.sonarr.get_all_series()
        count = 0
        for series in all_series:
            series_id = series.id
            series.episodes = self.sonarr.get_all_episodes(series_id=series_id)
            count += len(series.episodes)
        logger.info(
            f"Successfully retrieved {count} episodes from {len(all_series)} series."
        )
        return all_series

    def get_movie_searches(self, movies: list[arr_client.MovieModel]):
        movies_to_search = list[MovieSearch]()
        if not self.radarr:
            logger.debug("Radarr is not configured. Skipping...")
            return movies_to_search
        return [
            MovieSearch(movie_id=m.id, movie_title=m.title)
            for m in movies
            if self._can_movie_be_searched(movie=m)
        ]

    def get_season_searches(self, all_series: list[arr_client.SeriesModel]):
        seasons_to_search = set[SeasonSearch]()

        if not self.sonarr:
            logger.debug("Sonarr is not configured. Skipping...")
            return list(seasons_to_search)

        for series in all_series:
            for episode in series.episodes:
                if self._can_episode_be_searched(series=series, episode=episode):
                    seasons_to_search.add(
                        SeasonSearch(
                            series_id=series.id,
                            series_title=series.title,
                            season_number=episode.seasonNumber,
                        )
                    )
        return list(seasons_to_search)

    def wait_for_command(
        self,
        arr: arr_client.RadarrClient | arr_client.SonarrClient,
        command_id: int,
    ):
        arr_name = "Radarr" if isinstance(arr, arr_client.RadarrClient) else "Sonarr"
        start_time = datetime.now()
        while datetime.now() - start_time > timedelta(minutes=5):
            command_status = arr.get_command_status(id=command_id)
            logger.debug(f"Command Status: {command_status}")
            if command_status.status == "completed":
                return command_status.message

            time.sleep(10)
        logging.info(f"Timed out waiting for command {command_id} in {arr_name}")
        return "Timed out waiting for command"

    @classmethod
    def search(cls):
        upgraderr = cls()
        logger.info("Starting media search")

        movies = upgraderr.get_movies()
        all_series = upgraderr.get_all_series()

        searches = list[MovieSearch | SeasonSearch]()
        searches_triggered = 0

        searches.extend(upgraderr.get_movie_searches(movies=movies))
        searches.extend(upgraderr.get_season_searches(all_series=all_series))
        random.shuffle(searches)

        logger.debug(f"Found {len(searches)} searches to trigger")

        for media_search in searches[: settings.max_search_limit]:
            if upgraderr.dry_run:
                logger.info(f"DRY RUN: Skipping searching for {media_search}")
            elif isinstance(media_search, MovieSearch) and upgraderr.radarr:
                command = upgraderr.radarr.search_movie(
                    movie_ids=[media_search.movie_id]
                )
                logger.info(f"Triggering search for {media_search}")
                result = upgraderr.wait_for_command(
                    arr=upgraderr.radarr, command_id=command.id
                )
                log_and_notify_search(
                    message=f"Triggered search for {media_search}\nResult: {result}"
                )
            elif isinstance(media_search, SeasonSearch) and upgraderr.sonarr:
                command = upgraderr.sonarr.search_season(
                    series_id=media_search.series_id,
                    season_number=media_search.season_number,
                )
                logger.info(f"Triggering search for {media_search}")
                result = upgraderr.wait_for_command(
                    arr=upgraderr.sonarr, command_id=command.id
                )
                log_and_notify_search(
                    message=f"Triggered search for {media_search}\nResult: {result}"
                )
            searches_triggered += 1
        logger.info(f"Media searching completed. Queued {searches_triggered} searches.")

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
            upgraderr.search()
            return

        scheduler.add_job(
            func=Upgraderr.search_task, id="search", replace_existing=True
        )
        scheduler.start()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(prog="upgraderr")

    parser.add_argument(
        "action",
        choices=["search", "run", "clear"],
        help="""
        Sync the database with the Sonarr/Radarr instances.
        Search for new episodes/seasons.
        Run scheduler.
        Clear jobs from the scheduler.
        """,
    )

    args = parser.parse_args()

    if args.action == "search":
        Upgraderr.search()
    elif args.action == "run":
        Upgraderr.run()
    elif args.action == "clear":
        scheduler.remove_all_jobs()
