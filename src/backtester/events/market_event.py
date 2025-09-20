from backtester.events.event import Event
import time

class MarketEvent(Event):
  """
  Handles the event of receiving a new market update with corresponding bars.
  """
  def __init__(self, ticker: str):
    """
    Initialises the MarketEvent with a ticker indicating this ticker has a new movement in its price.
    Parameters:
    ticker - The ticker symbol, e.g. 'MSFT'.
    """
    self.type = "MARKET"
    self.ticker = ticker
    self.datetime = time.time()
