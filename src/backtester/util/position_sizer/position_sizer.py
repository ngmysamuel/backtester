from abc import ABC, abstractmethod

from backtester.portfolios.portfolio import Portfolio


class PositionSizer(ABC):
    @abstractmethod
    def get_position_size(self, portfolio: Portfolio):
        pass
