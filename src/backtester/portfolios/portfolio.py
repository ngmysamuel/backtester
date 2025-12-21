from abc import ABC, abstractmethod
from backtester.util.util import BarTuple


class Portfolio(ABC):
    """
    Abstract base class for all portfolio types.
    """

    @abstractmethod
    def on_signal(self, event):
        """
        Process a SignalEvent to generate an OrderEvent.
        """
        pass

    @abstractmethod
    def on_fill(self, event):
        """
        Process a FillEvent to update the portfolio's positions and holdings.
        """
        pass

    @abstractmethod
    def on_interval(self, history: dict[str, list[BarTuple]]):
        pass
