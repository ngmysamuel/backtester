import datetime
from abc import ABC, abstractmethod
from typing import NamedTuple  # identical to collections.namedtuple


class BarTuple(NamedTuple):
    Index: datetime.datetime
    open: float
    high: float
    low: float
    close: float
    volume: int
    raw_volume: int


class DataHandler(ABC):
    """
    Abstract base class for data handlers.
    """

    @abstractmethod
    def get_latest_bars(self, symbol: str, start_date: str, end_date: str):
        pass

    @abstractmethod
    def update_bars(self) -> BarTuple:
        """
        Note that the bars provided are NamedTuples.
        The time of each bar is found with the name "Index". The value is a pandas DateTime construct
        """
        pass
