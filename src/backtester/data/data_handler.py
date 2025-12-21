from backtester.util.util import BarTuple
from abc import ABC, abstractmethod

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
        The "Index" construct comes from the iterator returned from itertuples over the pandas dataframe
        """
        pass
