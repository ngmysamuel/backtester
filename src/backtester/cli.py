import collections
import importlib
import importlib.resources
import runpy
import sys
from pathlib import Path
from typing import Optional

import pandas as pd
import quantstats as qs
import typer
import yaml

from backtester.data.csv_data_handler import CSVDataHandler
from backtester.exceptions.negative_cash_exception import NegativeCashException
from backtester.execution.simulated_execution_handler import SimulatedExecutionHandler
from backtester.portfolios.naive_portfolio import NaivePortfolio

from rich import print as print_console

app = typer.Typer()

def load_config():
    """Loads the configuration from config.yaml."""
    try:
        # For Python 3.9+
        config_path = importlib.resources.files('backtester') / 'config.yaml'
        with config_path.open('r') as f:
            config = yaml.safe_load(f)
        return config
    except (AttributeError, ModuleNotFoundError):
        # Fallback for Python 3.7 and 3.8
        with importlib.resources.open_text('backtester', 'config.yaml') as f:
            config = yaml.safe_load(f)
        return config

def load_class(path_to_class: str):
    """Dynamically loads a class from a string."""
    module_path, class_name = path_to_class.rsplit('.', 1)
    m = importlib.import_module(module_path)
    return getattr(m, class_name)

@app.command()
def run(data_dir: str,
        data_source: Optional[str] = "csv",
        strategy: Optional[str] = "buy_and_hold_simple",
        slippage: Optional[str] = "multi_factor_slippage",
        exception_contd: Optional[int] = 0
      ):
  """
  Run the backtester with a given strategy and date range.
  args:
      data_dir (str): Directory containing CSV data files.
      strategy (str): the strategy to backtest; this name should match those found in config.yaml.
      slippage (str): the model used to calculate slippage
  """
  print_console(f"Data directory: [underline]{data_dir}[/underline], handled by: [underline]{data_source}[/underline]")
  print_console(f"Running backtest for strategy: [underline]{strategy}[/underline] with slippage modelling by: [underline]{slippage}[/underline]")

  config = load_config()  # load data from yaml config file

  backtester_settings = config["backtester_settings"]

  symbol_list = backtester_settings["symbol_list"]
  print_console(f"Symbols: {symbol_list}")

  initial_capital = backtester_settings["initial_capital"]
  start_timestamp = pd.to_datetime(backtester_settings["start_date"], dayfirst=True).timestamp()
  end_timestamp = pd.to_datetime(backtester_settings["end_date"], dayfirst=True).timestamp()
  interval = backtester_settings["interval"]
  exchange_closing_time = backtester_settings["exchange_closing_time"]
  benchmark_ticker = backtester_settings["benchmark"]
  atr_window = backtester_settings["atr_window"]
  print_console(f"Initial Capital: [underline]{initial_capital}[/underline]")

  event_queue = collections.deque()

  DataHandlerClass = load_class(config["data_handler"][data_source])
  if data_source == "yf":
    start_datetime = pd.to_datetime(start_timestamp, unit='s')
    start_date = start_datetime.strftime("%Y-%m-%d")
    end_datetime = pd.to_datetime(end_timestamp, unit='s')
    end_date = end_datetime.strftime("%Y-%m-%d")
    data_handler = DataHandlerClass(event_queue, start_date, end_date, symbol_list, interval, exchange_closing_time)
  else:
    data_handler = DataHandlerClass(event_queue, data_dir, symbol_list, interval, exchange_closing_time)

  SlippageClass = load_class(config["slippage"][slippage]["name"])
  slippage_settings = config["slippage"][slippage]["additional_parameters"] # TODO: handle NoSlippage model not having addition_parameters
  slippage_model = SlippageClass(data_handler.symbol_raw_data, slippage_settings) # TODO: handle NoSlippage model initialization
  slippage_model.generate_features()

  StrategyClass = load_class(config["strategies"][strategy]["name"])
  additional_params = config["strategies"][strategy].get("additional_parameters", {})
  strategy_instance = StrategyClass(event_queue, data_handler, **additional_params)

  portfolio = NaivePortfolio(data_handler,initial_capital,symbol_list,event_queue,start_timestamp, interval, atr_window=atr_window)

  execution_handler = SimulatedExecutionHandler(event_queue, data_handler, slippage_model)
  
  mkt_close = False

  while data_handler.continue_backtest:
    data_handler.update_bars()
    # Process events from the event queue (e.g., generate signals, execute orders, etc.)
    while event_queue:
      event = event_queue.popleft()
      if event.type == "MARKET":
        mkt_close = event.is_eod
        try:
          portfolio.on_market(event) # update portfolio valuation
        except NegativeCashException as e:
          if exception_contd:
            print(e)
          else:
            raise e
        execution_handler.on_market(event, mkt_close) # check if any orders can be filled, if so, it will update the portfolio via a FILL event
        strategy_instance.generate_signals(event) # generate signals based on market event
      elif event.type == "SIGNAL":
         portfolio.on_signal(event)
      elif event.type == "ORDER":
        execution_handler.on_order(event)
      elif event.type == "FILL":
        portfolio.on_fill(event)
    portfolio.end_of_interval()
    if mkt_close:
      portfolio.end_of_day() # deduct borrow costs and calculate margin
      mkt_close = False

  # portfolio.liquidate()
  portfolio.create_equity_curve()
  portfolio.equity_curve.to_csv("equity_curve.csv")

  benchmark_data_handler = CSVDataHandler(event_queue, data_dir, [benchmark_ticker], interval, exchange_closing_time)
  benchmark_data = benchmark_data_handler.symbol_raw_data["SPY"]
  benchmark_returns = benchmark_data["close"].pct_change()
  benchmark_returns.name = benchmark_ticker
  qs.reports.html(portfolio.equity_curve["returns"], benchmark=benchmark_returns, output='strategy_report.html', title=strategy, match_dates=False)


@app.command()
def dashboard():
  """
  Plot the results of the last backtest.
  """
  config = load_config()
  interval = config["backtester_settings"]["interval"]
  streamlit_script_path = Path("src/backtester/metrics/dashboard/streamlit_app.py").resolve()
  typer.echo(f"Loading [underline]{streamlit_script_path}[/underline]")
  sys.argv = ["streamlit", "run", streamlit_script_path, "--global.disableWidgetStateDuplicationWarning", "true", f" -- --interval {interval}"] # for more arguments, add ', " -- --what ee"' to the end
  runpy.run_module("streamlit", run_name="__main__")

if __name__ == "__main__":
  app()
