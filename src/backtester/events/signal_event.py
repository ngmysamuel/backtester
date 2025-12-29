from backtester.events.event import Event
from backtester.enums.signal_type import SignalType


class SignalEvent(Event):
    """
    Handles the event of sending a Signal from a Strategy object.
    """

    def __init__(self, timestamp: int, ticker: str, strategy: str, signal_type: SignalType, strength: float = 1.0):
        """
        Initialises the SignalEvent.

        Parameters:
        ticker - The ticker ticker, e.g. 'MSFT'.
        strategy - THe name of the strategy e.g. moving_average
        signal_type - 'LONG' or 'SHORT'.
        strength - An adjustment factor "suggestion" used to scale quantity at which the signal is generated.
        timestamp - The timestamp at which the signal was generated - simulated.
        """
        self.type = "SIGNAL"
        self.ticker = ticker
        self.strategy = strategy
        self.signal_type = signal_type
        self.strength = strength
        self.timestamp = timestamp
