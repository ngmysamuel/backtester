from abc import ABC, abstractmethod
import queue
from backtester.util.util import BarTuple

class Strategy(ABC):
    """
    Abstract base class for trading strategies.
    """
    def __init__(self, events: queue.Queue, symbol_list: list[str], interval: int):
        self.events = events
        self.symbol_list = symbol_list
        self.interval = interval

    def on_interval(self, history: dict[tuple[str,str], list[BarTuple]]):
        self.generate_signals(history)

    @abstractmethod
    def generate_signals(self, history: dict[tuple[str,str], list[BarTuple]]) -> None:
        pass
