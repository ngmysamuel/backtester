from backtester.events.event import Event

class MarketEvent(Event):
  """
  Handles the event of receiving a new market update with corresponding bars.
  """
  def __init__(self, ticker, op, high, low, close, volume):
    """
    Initialises the MarketEvent.
    """
    self.type = "MARKET"
    self.ticker = ticker
    self.open = op
    self.high = high
    self.low = low
    self.close = close
    self.volume = volume