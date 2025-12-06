# module to test: src/backtester/data/csv_data_handler.py
from backtester.data.csv_data_handler import CSVDataHandler
import os
import pandas as pd
from queue import Queue

# test init of CSVDataHandler
def test_init_csv_data_handler():
  event_queue = Queue()
  # assumes the test CSV files are located at the project's highest directory level
  csv_dir = os.path.dirname(os.path.dirname(os.path.dirname(__file__)))
  symbol_list = ["MSFT"]
  print(csv_dir)
  data_handler = CSVDataHandler(event_queue, csv_dir, pd.to_datetime("01/12/2023",format="%d/%m/%Y"), pd.to_datetime("01/12/2025",format="%d/%m/%Y"), symbol_list,"1d","16:00")
  assert data_handler.csv_dir == csv_dir
  assert data_handler.symbol_list == symbol_list
  assert data_handler.symbol_data is not None
  assert data_handler.latest_symbol_data is not None
  assert data_handler.continue_backtest is True