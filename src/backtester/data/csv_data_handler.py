from backtester.data.data_handler import DataHandler
import pandas as pd
import os
from backtester.events.market_event import MarketEvent

class CSVDataHandler(DataHandler):
  """
  CSVDataHandler is a concrete implementation of DataHandler that reads
  historical data for each symbol from CSV files.
  """

  def __init__(self, event_queue: list, csv_dir: str, symbol_list: str, interval: str, exchange_closing_time: str):
    """
    Initializes the CSVDataHandler
    args:
        event_queue: the Event Queue
        csv_dir: absolute directory path folder containing all the CSV files
        symbol_list: a list of symbol strings
        interval: e.g. 5m means OHLC data for 5 minutes
        exchange_closing_time: 24h time format - HH:MM
    """
    self.event_queue = event_queue
    self.csv_dir = csv_dir
    self.symbol_list = symbol_list
    self.interval = interval
    self.exchange_closing_time = exchange_closing_time

    self.symbol_raw_data = {}
    self.symbol_data = {}
    self.latest_symbol_data = {}
    self.continue_backtest = True

    self._load_from_csv()

  def _load_from_csv(self):
    """
    Opens the CSV files from the data directory, converting them into
    pandas DataFrames within a symbol dictionary. Assumes the format
    of the CSV files: date, open, high, low, close, volume
    """
    combined_index = None

    for symbol in self.symbol_list:
      # Load the CSV file
      df = pd.read_csv(
        os.path.join(self.csv_dir, f"{symbol}.csv"),
        header=0,
        parse_dates=True,
        usecols=lambda x: x.lower() in ["open", "close", "high", "low", "volume", "date"],
        converters={"Date": lambda x: pd.to_datetime(x).tz_localize(None)}
      )

      self.symbol_raw_data[symbol] = df
      self.symbol_data[symbol] = df
      self.latest_symbol_data[symbol] = []

      df.set_index("Date", inplace=True)
      df.sort_index(inplace=True) # ensure data is sorted
      df.columns = [col.lower() for col in df.columns]

      if combined_index is None:
        combined_index = df.index
      else:
        combined_index = combined_index.union(df.index) # include any dates not in the previous files

      self.symbol_data[symbol].to_csv("csv.csv")

    # Reindex the dataframes to the same index
    for symbol in self.symbol_list:
      self.symbol_data[symbol] = (
        self.symbol_data[symbol].reindex(index=combined_index, method="pad").itertuples()
      )

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
    for s in self.symbol_list:
      try:
        bar = next(self._get_new_bar(s))
      except StopIteration:
        self.continue_backtest = False
      else:
        if bar is not None:
          self.latest_symbol_data[s].append(bar)
          mkt_close = bar.Index + pd.Timedelta(self.interval) >= bar.Index.replace(hour=int(self.exchange_closing_time.split(":")[0]),minute=int(self.exchange_closing_time.split(":")[1]))
          self.event_queue.append(MarketEvent(bar.Index.timestamp(), mkt_close))


  def get_latest_bars(self, symbol: str, n: int = 1):
    """
    Returns the last N bars from the latest_symbol_data
    """
    return self.latest_symbol_data[symbol][-n:]