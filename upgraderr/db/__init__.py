from contextlib import contextmanager
from datetime import datetime, timezone

from sqlalchemy import TIMESTAMP, create_engine
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, sessionmaker

from upgraderr.settings import settings

database_url = f"sqlite:///{settings.data_directory}/db.sqlite3"
engine = create_engine(database_url)
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
    job_id: Mapped[str | None] = mapped_column(nullable=True)
    last_searched: Mapped[datetime | None] = mapped_column(nullable=True)


class Episode(Base):
    __tablename__ = "episodes"

    tvdb_id: Mapped[int] = mapped_column(primary_key=True)
    episode_id: Mapped[int] = mapped_column(nullable=False)
    episode_number: Mapped[int] = mapped_column(nullable=False)
    season_number: Mapped[int] = mapped_column(nullable=False)
    series_id: Mapped[int] = mapped_column(nullable=False)
    job_id: Mapped[str | None] = mapped_column(nullable=True)
    last_searched: Mapped[datetime | None] = mapped_column(nullable=True)
