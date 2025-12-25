import datetime
from abc import ABC, abstractmethod

from backtester.enums.direction_type import DirectionType
from backtester.util.util import BarTuple


class Slippage(ABC):
    """
    Abstract base class for all portfolio types.
    """

    @abstractmethod
    def on_interval(self, history: dict[str, list[BarTuple]]) -> None:
        pass

    @abstractmethod
    def calculate_slippage(self, ticker: str, trade_date: datetime.datetime, trade_size: float, direction: DirectionType) -> float:
        """
        Calculates the slippage for a particular trade based on the specifics of that trading day
        """
        pass
