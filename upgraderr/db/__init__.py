from contextlib import contextmanager
from datetime import datetime, timezone

from sqlalchemy import TIMESTAMP, create_engine, ForeignKey
from sqlalchemy.orm import (
    DeclarativeBase,
    Mapped,
    mapped_column,
    sessionmaker,
    relationship,
)

from upgraderr.settings import settings

database_url = f"sqlite:///{settings.data_directory}/db.sqlite3"
engine = create_engine(database_url, echo=True)
session_maker = sessionmaker(engine, expire_on_commit=False)


@contextmanager
def get_db_session():
    with session_maker() as session:
        yield session


class Base(DeclarativeBase):
    created_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
    )
    modified_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True),
        nullable=True,
        onupdate=lambda: datetime.now(timezone.utc),
    )


class Movie(Base):
    __tablename__ = "movies"

    # Refers to the tmdb id
    id: Mapped[int] = mapped_column(primary_key=True)
    radarr_id: Mapped[int] = mapped_column(nullable=False)

    commands: Mapped[list["MovieCommand"]] = relationship(
        "MovieCommand", back_populates="movie"
    )

    def __init__(self, id: int, **kw):
        super().__init__(id=id, **kw)


class MovieCommand(Base):
    __tablename__ = "movie_commands"

    id: Mapped[int] = mapped_column(primary_key=True)
    movie_id: Mapped[int] = mapped_column(
        ForeignKey(
            Movie.id,
            onupdate="CASCADE",
            ondelete="CASCADE",
            name="movie_commands_movie_id_fkey",
        )
    )
    reason: Mapped[str] = mapped_column(nullable=False)
    queued: Mapped[datetime | None] = mapped_column(nullable=True)
    started: Mapped[datetime | None] = mapped_column(nullable=True)
    ended: Mapped[datetime | None] = mapped_column(nullable=True)

    movie: Mapped[Movie] = relationship(Movie, back_populates="commands")

    def __init__(
        self,
        id: int,
        movie_id: int,
        reason: str,
        queued: datetime | None = None,
        started: datetime | None = None,
        ended: datetime | None = None,
        **kw,
    ):
        super().__init__(
            id=id,
            movie_id=movie_id,
            reason=reason,
            queued=queued,
            started=started,
            ended=ended,
            **kw,
        )


class Episode(Base):
    __tablename__ = "episodes"

    id: Mapped[int] = mapped_column(primary_key=True)
    episode_number: Mapped[int] = mapped_column(primary_key=True)
    season_number: Mapped[int] = mapped_column(primary_key=True)
    series_id: Mapped[int] = mapped_column(primary_key=True)

    commands: Mapped[list["EpisodeCommand"]] = relationship(
        "EpisodeCommands", back_populates="episode"
    )

    def __init__(
        self,
        id: int,
        episode_number: int,
        season_number: int,
        series_id: int,
        **kw,
    ):
        super().__init__(
            id=id,
            episode_number=episode_number,
            season_number=season_number,
            series_id=series_id,
            **kw,
        )


class EpisodeCommand(Base):
    __tablename__ = "episode_commands"

    id: Mapped[int] = mapped_column(primary_key=True)
    episode_id: Mapped[int] = mapped_column(
        ForeignKey(
            Episode.id,
            onupdate="CASCADE",
            ondelete="CASCADE",
            name="episode_commands_episode_id_fkey",
        )
    )
    reason: Mapped[str] = mapped_column(nullable=False)
    queued: Mapped[datetime | None] = mapped_column(nullable=True)
    started: Mapped[datetime | None] = mapped_column(nullable=True)
    ended: Mapped[datetime | None] = mapped_column(nullable=True)

    episode: Mapped[Episode] = relationship(Episode, back_populates="commands")

    def __init__(
        self,
        id: int,
        episode_id: int,
        reason: str,
        queued: datetime | None = None,
        started: datetime | None = None,
        ended: datetime | None = None,
        **kw,
    ):
        super().__init__(
            id=id,
            episode_id=episode_id,
            reason=reason,
            queued=queued,
            started=started,
            ended=ended,
            **kw,
        )
