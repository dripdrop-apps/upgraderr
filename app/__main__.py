import argparse
import logging
import logging.handlers
import random
import sys
import time
from app.arr import radarr, sonarr
from app.notifications import send_search_notification, apprise
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


def log_and_notify(message: str, level=apprise.NotifyType.INFO):
    log_level = logging.INFO
    if level == apprise.NotifyType.FAILURE:
        log_level = logging.ERROR
    elif level == apprise.NotifyType.WARNING:
        log_level = logging.WARNING

    logger.log(level=log_level, msg=message)
    send_search_notification(body=message, level=level)


class Upgraderr:
    def __init__(self):
        self.sonarr = sonarr.SonarrClient.initialize()
        self.radarr = radarr.RadarrClient.initialize()
        self.dry_run = settings.dry_run
        if self.dry_run:
            logger.info("DRY RUN: No searches will be executed.")

    def get_movie_searches(self):
        searchable_movies = list[radarr.MovieModel]()
        if not self.radarr:
            logger.info("Radarr is not configured. Skipping...")
            return searchable_movies
        movies = self.radarr.get_all_movies()
        logger.info(f"Successfully retrieved {len(movies)} movies")
        for m in movies:
            check = m.can_be_searched()
            if check.should_search:
                logger.debug(f"Movie {m} is searchable. Reason: {check.reason}")
                searchable_movies.append(m)
            else:
                logger.debug(f"Skipping movie: {m}. Reason: {check.reason}")
        return searchable_movies

    def get_season_searches(self):
        searchable_seasons = list[sonarr.SeasonModel]()
        if not self.sonarr:
            logger.debug("Sonarr is not configured. Skipping...")
            return searchable_seasons
        all_series = self.sonarr.get_all_series()
        episodes_count = 0
        for series in all_series:
            for season in series.seasons:
                check = season.can_be_searched()
                if check.should_search:
                    logger.debug(
                        f"Season {season} is searchable. Reason: {check.reason}"
                    )
                else:
                    logger.debug(
                        f"Skipping season: {season}. Reason: No upgradable episode"
                    )
                episodes_count += len(season.episodes)
        logger.info(
            f"Successfully retrieved {len(all_series)} series with {episodes_count} episodes"
        )
        return searchable_seasons

    def search(self):
        logger.info("Starting media search")

        searchable_media = list[sonarr.SeasonModel | radarr.MovieModel]()
        searchable_media.extend(self.get_movie_searches())
        searchable_media.extend(self.get_season_searches())
        searches_triggered = 0

        random.shuffle(searchable_media)

        logger.debug(f"Found {len(searchable_media)} searches to trigger")

        for media in searchable_media[: settings.max_search_limit]:
            if self.dry_run:
                logger.info(
                    f"DRY RUN: Skipping searching for {media.media_type}: {media}"
                )
            result = media.search()
            log_and_notify(
                message=result.message,
                level=apprise.NotifyType.INFO
                if result.success
                else apprise.NotifyType.FAILURE,
            )
            searches_triggered += 1

        logger.info(f"Media searching completed. Queued {searches_triggered} searches.")

    @classmethod
    def run(cls):
        while True:
            upgraderr = cls()
            try:
                upgraderr.search()
            except Exception as e:
                logger.info(f"Error during search: {e}", exc_info=True)
            if settings.one_shot:
                return
            logger.info(f"Waiting {settings.search_interval} minutes for next run.")
            time.sleep(60 * settings.search_interval)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(prog="upgraderr")

    parser.add_argument(
        "action",
        choices=["run"],
        help="""Search for new episodes/seasons.""",
    )

    args = parser.parse_args()

    if args.action == "run":
        Upgraderr.run()
