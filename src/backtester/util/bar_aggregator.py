from backtester.util.util import BarTuple
from backtester.data.data_handler import DataHandler
from backtester.events.market_event import MarketEvent


class BarAggregator:
    def __init__(self, base_interval: int, interval: int, ticker: str, data_handler: DataHandler):
        self.base_interval = base_interval
        self.interval = interval
        self.ticker = ticker
        self.data_handler = data_handler
        self.interval_start_time = None
        self.bar = {}

    def on_heartbeat(self, event: MarketEvent) -> BarTuple | None:
        """
        Aggregates heartbeats into bars e.g. 5 min bars means the high,low
        prices within the last 5min. The open price at the beginning of 5min
        and the close price at the end of 5min
        """
        to_return = None
        if self.interval_start_time is None:
            self.interval_start_time = event.timestamp

        bar = self.data_handler.get_latest_bars(self.ticker)[0] # get the base frequency's latest data

        if self.bar:
            self.bar["high"] = max(self.bar["high"], bar.high)
            self.bar["low"] = min(self.bar["low"], bar.low)
            self.bar["close"] = bar.close
            self.bar["volume"] += bar.volume
        else:
            self.bar["Index"] = bar.Index
            self.bar["open"] = bar.open
            self.bar["high"] = bar.high
            self.bar["low"] = bar.low
            self.bar["close"] = bar.close
            self.bar["volume"] = bar.volume
            self.bar["raw_volume"] = None

        if event.timestamp >= self.interval_start_time + self.interval - self.base_interval: # start of a new interval
            to_return = BarTuple(**self.bar)
            self.bar = {}
            self.interval_start_time = self.interval_start_time + self.interval

        return to_return
