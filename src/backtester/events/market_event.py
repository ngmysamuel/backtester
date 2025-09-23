from backtester.events.event import Event

class MarketEvent(Event):
  """
  Handles the event of receiving a new market update with corresponding bars.
  """
  def __init__(self, timestamp: float):
    """
    Initialises the MarketEvent with a ticker indicating this ticker has a new movement in its price.
    Parameters:
    timestamp - The timestamp at which the market event was generated - simulated.
    """
    self.type = "MARKET"
    self.timestamp = timestamp
