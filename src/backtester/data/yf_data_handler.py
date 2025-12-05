import queue
from datetime import datetime
from typing import Union

import pandas as pd
import yfinance as yf

from backtester.data.data_handler import DataHandler
from backtester.events.market_event import MarketEvent


class YFDataHandler(DataHandler):
  def __init__(self, event_queue: queue.Queue, start_date: Union[pd.Timestamp, datetime], end_date: Union[pd.Timestamp, datetime], symbol_list: str, interval: str, exchange_closing_time: str):
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
    self.start_date = start_date
    self.end_date = end_date
    self.symbol_list = symbol_list
    self.interval = interval
    self.exchange_closing_time = exchange_closing_time

    self.symbol_raw_data = {}
    self.symbol_data = {}
    self.latest_symbol_data = {}
    self.continue_backtest = True

    self._download_from_yf()

  def _download_from_yf(self):
    """
    Handler method to pull data from yfinance
    """
    combined_index = None
    start = self.start_date.strftime("%Y-%m-%d")
    end = self.end_date.strftime("%Y-%m-%d")

    for symbol in self.symbol_list:
      df = yf.download(symbol, start=start, end=end, interval=self.interval, multi_level_index=False)
      df = df[["Open", "High", "Low", "Close", "Volume"]]

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
      self.symbol_data[symbol] = self.symbol_data[symbol].reindex(index=combined_index, method="pad").itertuples()

  def _get_new_bar(self, symbol: str):
    """
    Returns the latest bar from the data feed as a tuple of
    (datetime, open, high, low, close, volume).
    """
    for b in self.symbol_data[symbol]:
      yield b

  def update_bars(self):
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

    self.event_queue.put(MarketEvent(start_time, mkt_close))

  def get_latest_bars(self, symbol: str, n: int = 1):
    """
    Returns the last N bars from the latest_symbol_data
    """
    return self.latest_symbol_data[symbol][-n:]
