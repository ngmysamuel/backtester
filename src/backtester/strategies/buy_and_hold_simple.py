from backtester.strategies.strategy import Strategy
from backtester.events.signal_event import SignalEvent
from backtester.enums.signal_type import SignalType
import queue
from backtester.util.util import BarTuple

class BuyAndHoldSimple(Strategy):
    def __init__(self, events: queue.Queue, name: str, **kwargs):
        super().__init__(events, name, kwargs["symbol_list"], kwargs["interval"])
        self.days_before_buying = kwargs.get("days_before_buying", 21)
        self.bought = {sym: False for sym in self.symbol_list}
        self.counter = 0

    def generate_signals(self, histories: dict[tuple[str,str], list[BarTuple]]):
        self.counter += 1
        for (ticker,interval), history in histories.items():
            # No market data available for this ticker at the moment; skip signal generation.
            if not history:
                continue
            timestamp = history[-1].Index.timestamp()

            if not self.bought[ticker] and self.counter >= self.days_before_buying:
                self.bought[ticker] = True
                self.events.put(SignalEvent(timestamp, ticker, self.name, SignalType.LONG))
