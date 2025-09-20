from abc import ABC, abstractmethod

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