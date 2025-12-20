from abc import ABC, abstractmethod

from backtester.portfolios.portfolio import Portfolio
from backtester.util.util import BarTuple

class PositionSizer(ABC):
    @abstractmethod
    def on_interval(self, history: dict[str, list[BarTuple]]):
        pass
    @abstractmethod
    def get_position_size(self, portfolio: Portfolio):
        pass
