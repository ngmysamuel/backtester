from backtester.strategies.strategy import Strategy
from backtester.data.data_handler import DataHandler
from backtester.events.event import Event
from backtester.events.signal_event import SignalEvent
from backtester.enums.signal_type import SignalType
import queue


class BuyAndHoldSimple(Strategy):
    def __init__(self, events: queue.Queue, data_handler: DataHandler):
        self.events = events
        self.data_handler = data_handler
        self.symbol_list = self.data_handler.symbol_list
        self.bought = {sym: False for sym in self.symbol_list}

    def generate_signals(self, event: Event):
        timestamp = event.timestamp
        ticker = event.ticker

        for ticker in self.symbol_list:
            # Retrieve latest bar(s) for ticker. If no data is available, do not generate a signal.
            ohlcv_data = self.data_handler.get_latest_bars(ticker, n=1)

            # No market data available for this ticker at the moment; skip signal generation.
            if not ohlcv_data:
                continue

            if not self.bought[ticker]:
                self.bought[ticker] = True
                self.events.put(SignalEvent(timestamp, ticker, SignalType.LONG))
