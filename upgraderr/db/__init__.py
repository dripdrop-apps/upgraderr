from contextlib import contextmanager
from datetime import datetime, timezone

from sqlalchemy import TIMESTAMP, create_engine
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, sessionmaker

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
    tmdb_id: Mapped[int] = mapped_column(primary_key=True)
    movie_id: Mapped[int] = mapped_column(nullable=False)
    last_searched: Mapped[datetime | None] = mapped_column(nullable=True)

    def __init__(
        self, tmdb_id: int, movie_id: int, last_searched: datetime | None = None, **kw
    ):
        super().__init__(
            tmdb_id=tmdb_id, movie_id=movie_id, last_searched=last_searched, **kw
        )


class Episode(Base):
    __tablename__ = "episodes"

    tvdb_id: Mapped[int] = mapped_column(primary_key=True)
    episode_id: Mapped[int] = mapped_column(nullable=False)
    episode_number: Mapped[int] = mapped_column(nullable=False)
    season_number: Mapped[int] = mapped_column(nullable=False)
    series_id: Mapped[int] = mapped_column(nullable=False)
    last_searched: Mapped[datetime | None] = mapped_column(nullable=True)

    def __init__(
        self,
        tvdb_id: int,
        episode_id: int,
        episode_number: int,
        season_number: int,
        series_id: int,
        last_searched: datetime | None = None,
        **kw,
    ):
        super().__init__(
            tvdb_id=tvdb_id,
            episode_id=episode_id,
            episode_number=episode_number,
            season_number=season_number,
            series_id=series_id,
            last_searched=last_searched,
            **kw,
        )
