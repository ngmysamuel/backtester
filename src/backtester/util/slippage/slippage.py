from abc import ABC, abstractmethod
from backtester.util.util import BarTuple


class Slippage(ABC):
    """
    Abstract base class for all portfolio types.
    """

    @abstractmethod
    def on_interval(self, history: dict[str, list[BarTuple]]):
        pass

    @abstractmethod
    def calculate_slippage(self, ticker, trade_date, trade_size):
        """
        Calculates the slippage for a particular trade based on the specifics of that trading day
        """
        pass
