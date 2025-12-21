from backtester.events.event import Event


class MarketEvent(Event):
    """
    Handles the event of receiving a new market update with corresponding bars.
    """

    def __init__(self, timestamp: float, is_eod: bool):
        """
        Initialises the MarketEvent with a ticker indicating this ticker has a new movement in its price.
        args:
            timestamp - The timestamp at which the market event was generated, simulated.
            is_eod - to signify the end of the trading day
        """
        self.type = "MARKET"
        self.timestamp = timestamp
        self.is_eod = is_eod
