from sqlalchemy import create_engine

from app.settings import settings

database_url = f"sqlite:///{settings.data_directory}/db.sqlite3"
engine = create_engine(database_url)
