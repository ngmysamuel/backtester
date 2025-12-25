import queue
from datetime import datetime
from typing import Any, Iterator

import pandas as pd
import yfinance as yf

from backtester.data.data_handler import DataHandler
from backtester.events.event import Event
from backtester.events.market_event import MarketEvent
from backtester.util.util import BarTuple


class YFDataHandler(DataHandler):
    def __init__(self, event_queue: queue.Queue[Event], **kwargs):
        """
        Initializes the YFDataHandler
        args:
            event_queue: the Event Queue
            start_date: start date of the backtest
            end_date: end date of the backtest
            symbol_list: a list of symbol strings
            interval: e.g. 5m means OHLC data for 5 minutes
            exchange_closing_time: 24h time format - HH:MM
        """
        self.event_queue = event_queue
        self.start_date: pd.Timestamp | datetime = pd.to_datetime(kwargs["start_date"], dayfirst=True)
        self.end_date: pd.Timestamp | datetime = pd.to_datetime(kwargs["end_date"], dayfirst=True)
        self.symbol_list: str = kwargs["symbol_list"]
        self.interval: str = kwargs["base_interval"]
        self.exchange_closing_time: str = kwargs["exchange_closing_time"]

        self.symbol_raw_data: dict[str, pd.DataFrame] = {}
        self.symbol_data: dict[str, Any] = {} # str => pd.DataFrame | Iterator[Any]
        self.latest_symbol_data: dict[str, list[BarTuple]] = {}
        self.continue_backtest = True

        self._download_from_yf()

    def _download_from_yf(self) -> None:
        """
        Handler method to pull data from yfinance
        """
        combined_index = None
        start = self.start_date.strftime("%Y-%m-%d")
        end = self.end_date.strftime("%Y-%m-%d")

        for symbol in self.symbol_list:
            df = yf.download(symbol, start=start, end=end, interval=self.interval, multi_level_index=False)
            df.columns = [str(col).lower() for col in df.columns]
            df = df[["open", "high", "low", "close", "volume"]]
            df.index = df.index.tz_localize(None)

            self.symbol_raw_data[symbol] = df
            self.symbol_data[symbol] = df
            self.latest_symbol_data[symbol] = []

            df.sort_index(inplace=True)  # ensure data is sorted
            df.columns = [col.lower() for col in df.columns]

            if combined_index is None:
                combined_index = df.index
            else:
                combined_index = combined_index.union(df.index)  # include any dates not in the previous files

        for symbol in self.symbol_list:
            tmp = self.symbol_data[symbol].reindex(index=combined_index)
            price_cols = ["open", "high", "low", "close"]
            tmp[price_cols] = tmp[price_cols].fillna(method="pad")
            tmp["volume"] = tmp["volume"].fillna(0)
            self.symbol_data[symbol] = tmp.itertuples()

    def _get_new_bar(self, symbol: str) -> Iterator[Any]:
        """
        Returns the latest bar from the data feed as a tuple of
        (datetime, open, high, low, close, volume).
        """
        for b in self.symbol_data[symbol]:
            yield b

    def update_bars(self) -> None:
        """
        Pushes the latest bar to the latest_symbol_data structure for all
        symbols in the symbol list. This will also generate a MarketEvent.
        """
        mkt_close = False
        start_time = None
        for s in self.symbol_list:
            try:
                bar = next(self._get_new_bar(s))
            except StopIteration:
                self.continue_backtest = False
                return
            else:
                if bar is not None:
                    self.latest_symbol_data[s].append(bar)
                    mkt_close = bar.Index + pd.Timedelta(self.interval) >= bar.Index.replace(hour=int(self.exchange_closing_time.split(":")[0]), minute=int(self.exchange_closing_time.split(":")[1]))
                    start_time = bar.Index.timestamp()

        if start_time is not None:
            self.event_queue.put(MarketEvent(start_time, mkt_close))

    def get_latest_bars(self, symbol: str, n: int = 1) -> list[BarTuple]:
        """
        Returns the last N bars from the latest_symbol_data
        """
        return self.latest_symbol_data[symbol][-n:]
