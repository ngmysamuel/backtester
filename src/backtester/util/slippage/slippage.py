from abc import ABC, abstractmethod


class Slippage(ABC):
    """
    Abstract base class for all portfolio types.
    """

    @abstractmethod
    def calculate_slippage(self, ticker, trade_date, trade_size):
        """
        Calculates the slippage for a particular trade based on the specifics of that trading day
        """
        pass

    @abstractmethod
    def on_market(self, ticker, trade_date, trade_size):
        """
        Updates the slippage model with specifics from the market
        """
        pass