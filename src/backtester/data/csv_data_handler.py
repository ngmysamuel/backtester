import os
import queue
from datetime import datetime
from typing import Any, Iterator

import pandas as pd

from backtester.data.data_handler import DataHandler
from backtester.events.event import Event
from backtester.events.market_event import MarketEvent
from backtester.util.util import BarTuple
from backtester.util.util import str_to_pandas


class CSVDataHandler(DataHandler):
    """
    CSVDataHandler is a concrete implementation of DataHandler that reads
    historical data for each symbol from CSV files.
    """

    def __init__(self, event_queue: queue.Queue[Event], **kwargs):
        """
        Initializes the CSVDataHandler
        args:
            event_queue: the Event Queue
            csv_dir: absolute directory path folder containing all the CSV files
            start_date: start date of the backtest
            end_date: end date of the backtest
            symbol_list: a list of symbol strings
            interval: e.g. 5m means OHLC data for 5 minutes
            exchange_closing_time: 24h time format - HH:MM
        """
        self.event_queue = event_queue
        self.csv_dir: str = kwargs["data_dir"]
        self.start_date: pd.Timestamp | datetime = pd.to_datetime(kwargs["start_date"], dayfirst=True)
        self.end_date: pd.Timestamp | datetime = pd.to_datetime(kwargs["end_date"], dayfirst=True)
        self.symbol_list: str = kwargs["symbol_list"]
        self.interval: str = kwargs["base_interval"]
        self.exchange_closing_time: str = kwargs["exchange_closing_time"]

        self.symbol_raw_data: dict[str, pd.DataFrame] = {}
        self.symbol_data: dict[str, Any] = {} # str => pd.DataFrame | Iterator[Any]
        self.latest_symbol_data: dict[str, list[BarTuple]] = {}
        self.continue_backtest = True

        self._load_from_csv()

    def _load_from_csv(self) -> None:
        """
        Opens the CSV files from the data directory, converting them into
        pandas DataFrames within a symbol dictionary. Assumes the format
        of the CSV files: date, open, high, low, close, volume
        """
        combined_index = None

        for symbol in self.symbol_list:
            # Load the CSV file
            df = pd.read_csv(
              os.path.join(self.csv_dir, f"{symbol}_{self.interval}.csv"),
              header=0,
              parse_dates=True,
            )

            df.columns = [str(col).lower() for col in df.columns]
            index_col = "date" if "date" in df.columns else "datetime"
            df = df[["open", "close", "high", "low", "volume", index_col]]

            df[index_col] = pd.to_datetime(df[index_col], utc=True).dt.tz_localize(None)
            df.set_index(index_col, inplace=True)
            df.sort_index(inplace=True)  # ensure data is sorted

            df = df.loc[self.start_date : self.end_date] # type: ignore [misc]

            self.symbol_raw_data[symbol] = df
            self.symbol_data[symbol] = df
            self.latest_symbol_data[symbol] = []

            if combined_index is None:
                combined_index = pd.date_range(self.start_date, self.end_date, freq=str_to_pandas(self.interval))
            else:
                combined_index = combined_index.union(df.index)  # include any dates not in the previous files

        # Reindex the dataframes to the same index
        for symbol in self.symbol_list:
            self.symbol_data[symbol] = self.symbol_data[symbol].reindex(index=combined_index, method="pad").itertuples()

    def _get_new_bar(self, symbol: str) -> Iterator[Any]:
        """
        Returns the latest bar from the data feed as a tuple of
        (datetime, open, high, low, close, volume).
        """
        for b in self.symbol_data[symbol]:
            yield b

    def update_bars(self) -> None:
        """
        TODO: to be made more memory efficient - there are 2 copies here, and another in bar_manager.py
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
