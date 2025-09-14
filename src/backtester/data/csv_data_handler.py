from data_handler import DataHandler
import pandas as pd
import os

class CSVDataHandler(DataHandler):
  """
  CSVDataHandler is a concrete implementation of DataHandler that reads
  historical data for each symbol from CSV files.
  """

  def __init__(self, event_queue: list, csv_dir: str, symbol_list: str):
    """
    Initializes the CSVDataHandler
    args:
        event_queue: the Event Queue
        csv_dir: absolute directory path folder containing all the CSV files
        symbol_list: a list of symbol strings
    """
    self.event_queue = event_queue
    self.csv_dir = csv_dir
    self.symbol_list = symbol_list

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
    comb_index = None

    for s in self.symbol_list:
      # Load the CSV file with no header information, indexed on date
      df = pd.read_csv(
        os.path.join(self.csv_dir, f"{s}.csv"),
        header=0,
        index_col=0,
        parse_dates=True,
        names=[
          "date",
          "open",
          "high",
          "low",
          "close",
          "volume",
          "dividends",
          "stocksplits"
        ],
      )

      df.sort_index(inplace=True)

      self.symbol_data[s] = df
      self.latest_symbol_data[s] = []

      if comb_index is None:
        comb_index = df.index
      else: # include any dates not in the previous file
        comb_index = comb_index.union(df.index)

    # Reindex the dataframes to the same index
    for s in self.symbol_list:
      self.symbol_data[s] = (
        self.symbol_data[s].reindex(index=comb_index, method="pad").iterrows()
      )

  def _get_new_bar(self, symbol):
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
    pass

  def get_latest_bars(self, symbol, N=1):
    """
    Returns the last N bars from the latest_symbol_data
    """
    return self.latest_symbol_data[symbol][-N:]