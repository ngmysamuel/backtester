from typing import Optional
import datetime
from backtester.data.data_handler import DataHandler
from backtester.events.market_event import MarketEvent
from backtester.util.util import BarTuple, BarDict, SentimentTuple

class BarAggregator:
    def __init__(self, base_interval: int, interval: int, ticker: str, data_handler: DataHandler):
        self.base_interval = base_interval
        self.interval = interval
        self.ticker = ticker
        self.data_handler = data_handler
        self.interval_start_time: Optional[float] = None
        self.bar: Optional[BarDict] = None 

    def on_heartbeat(self, event: MarketEvent) -> BarTuple | None:
        """
        Aggregates heartbeats into bars e.g. 5 min bars means the high,low
        prices within the last 5min. The open price at the beginning of 5min
        and the close price at the end of 5min
        """
        to_return = None
        if self.interval_start_time is None:
            self.interval_start_time = event.timestamp

        bars = self.data_handler.get_latest_bars(self.ticker)
        if not bars: # there is entirely no data at all - typically when using the live data handler off trading hours
            return
        bar = bars[-1]  # get the base frequency's latest data

        if self.bar:
            self.bar["high"] = max(self.bar["high"], bar.high)
            self.bar["low"] = min(self.bar["low"], bar.low)
            self.bar["close"] = bar.close
            self.bar["volume"] += bar.volume
        else:
            self.bar = {
                "Index": bar.Index,
                "open": bar.open,
                "high": bar.high,
                "low": bar.low,
                "close": bar.close,
                "volume": bar.volume,
                "sentiment": SentimentTuple(Index=datetime.datetime.now(), score=0.0),
                "raw_volume": None
            }

        if event.timestamp >= self.interval_start_time + self.interval - self.base_interval:  # start of a new interval
            if self.bar:
                to_return = BarTuple(**self.bar)
            self.bar = None
            self.interval_start_time = self.interval_start_time + self.interval

        return to_return
