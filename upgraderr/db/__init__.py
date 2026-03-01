from contextlib import contextmanager
from datetime import datetime, timezone

from sqlalchemy import TIMESTAMP, create_engine
from sqlalchemy.orm import (
    DeclarativeBase,
    Mapped,
    mapped_column,
    sessionmaker,
)

from upgraderr.settings import settings

database_url = f"sqlite:///{settings.data_directory}/db.sqlite3"
engine = create_engine(database_url, echo=True)
session_maker = sessionmaker(engine, expire_on_commit=False)


@contextmanager
def get_session():
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

    id: Mapped[int] = mapped_column(primary_key=True)
    search_reason: Mapped[str] = mapped_column(nullable=True)
    last_searched: Mapped[datetime] = mapped_column(TIMESTAMP(), nullable=True)

    def __init__(
        self,
        id: int,
        search_reason: str | None = None,
        last_searched: datetime | None = None,
        **kw,
    ):
        super().__init__(
            id=id, search_reason=search_reason, last_searched=last_searched, **kw
        )


class Episode(Base):
    __tablename__ = "episodes"

    episode_number: Mapped[int] = mapped_column(primary_key=True)
    season_number: Mapped[int] = mapped_column(primary_key=True)
    series_id: Mapped[int] = mapped_column(primary_key=True)
    search_reason: Mapped[str] = mapped_column(nullable=True)
    last_searched: Mapped[datetime] = mapped_column(TIMESTAMP(), nullable=True)

    def __init__(
        self,
        episode_number: int,
        season_number: int,
        series_id: int,
        search_reason: str | None = None,
        last_searched: datetime | None = None,
        **kw,
    ):
        super().__init__(
            episode_number=episode_number,
            season_number=season_number,
            series_id=series_id,
            search_reason=search_reason,
            last_searched=last_searched,
            **kw,
        )


class Job(Base):
    __tablename__ = "jobs"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement="auto")

    def __init__(self, id: int | None = None, **kw):
        super().__init__(id=id, **kw)
