from abc import ABC, abstractmethod

class Slippage(ABC):
  """
  Abstract base class for all portfolio types.
  """
  
  @abstractmethod
  def generate_features(self):
    """
    Generates features required to model slippage based on OHLC data
    """
    pass

  @abstractmethod
  def calculate_slippage(self, trade_date, trade_size):
    """
    Calculates the slippage for a particular trade based on the specifics of that trading day
    """
    pass