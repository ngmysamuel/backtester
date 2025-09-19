from abc import ABC, abstractmethod


class DataHandler(ABC):
  """
  Abstract base class for data handlers.
  """
  @abstractmethod
  def get_latest_bars(self, symbol: str, start_date: str, end_date: str):
    pass

  @abstractmethod
  def update_bars(self):
    pass
