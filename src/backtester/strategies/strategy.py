from abc import ABC, abstractmethod
from backtester.events.event import Event


class Strategy(ABC):
    """
    Abstract base class for trading strategies.
    """

    @abstractmethod
    def generate_signals(self, event: Event):
        pass
