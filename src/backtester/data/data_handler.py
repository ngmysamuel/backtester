from abc import ABC, abstractmethod

from backtester.util.util import BarTuple


class DataHandler(ABC):
    """
    Abstract base class for data handlers.
    """

    @abstractmethod
    def get_latest_bars(self, symbol: str, n: int = None) -> list[BarTuple]:
        pass

    @abstractmethod
    def update_bars(self) -> None:
        """
        Note that the bars provided are NamedTuples.
        The time of each bar is found with the name "Index". The value is a pandas DateTime construct
        The "Index" construct comes from the iterator returned from itertuples over the pandas dataframe
        """
        pass
