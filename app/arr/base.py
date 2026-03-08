import cachetools
import requests
from pydantic import BaseModel
from typing import Literal, TypeVar, Generic

T = TypeVar("T")

COMMAND_TIMEOUT = 10


class ArrClient(Generic[T], requests.Session):
    def __init__(self, url: str, api_key: str | None = None):
        super().__init__()
        self.cache = cachetools.Cache(maxsize=120)
        self.base_url = url
        if api_key:
            self.headers.update({"X-Api-Key": api_key})

    def request(self, method: str, url: str, *args, **kwargs):
        response = super().request(
            method,
            f"{self.base_url}{url}",
            *args,
            **kwargs,
            timeout=COMMAND_TIMEOUT * 60,
        )
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


class CommandStatus(BaseModel):
    id: int
    commandName: str
    message: str | None = None
    status: Literal["queued", "completed", "started"]
