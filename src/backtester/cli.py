import typer
from typing import Optional
from backtester.data.csv_data_handler import CSVDataHandler
import collections
import yaml
import importlib.resources
import importlib
from backtester.portfolios.naive_portfolio import NaivePortfolio
import pandas as pd
from backtester.execution.simulated_execution_handler import SimulatedExecutionHandler
from backtester.exceptions.negative_cash_exception import NegativeCashException

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
        strategy: Optional[str] = "buy_and_hold_simple",
        exception_contd: Optional[int] = 0
      ):
  """
  Run the backtester with a given strategy and date range.
  args:
      data_dir (str): Directory containing CSV data files.
      strategy (str): the strategy to backtest; this name should match those found in config.yaml.
  """
  typer.echo(f"Data directory: {data_dir}")
  typer.echo(f"Running backtest for strategy: {strategy}")

  config = load_config()  # load data from yaml config file

  symbol_list = config["backtester_settings"]["symbol_list"]
  typer.echo(f"Symbols: {symbol_list}")

  initial_capital = config["backtester_settings"]["initial_capital"]
  start_timestamp = pd.to_datetime(config["backtester_settings"]["start_date"]).timestamp()
  interval = config["backtester_settings"]["interval"]
  exchange_closing_time = config["backtester_settings"]["exchange_closing_time"]
  typer.echo(f"Initial Capital: {initial_capital}")
  

  StrategyClass = load_class(config["strategies"][strategy]["name"])
  additional_params = config["strategies"][strategy].get("additional_parameters", {})

  event_queue = collections.deque()
  data_handler = CSVDataHandler(event_queue, data_dir, symbol_list, interval, exchange_closing_time)
  strategy_instance = StrategyClass(event_queue, data_handler, **additional_params)
  portfolio = NaivePortfolio(data_handler,initial_capital,symbol_list,event_queue,start_timestamp)
  execution_handler = SimulatedExecutionHandler(event_queue, data_handler)
  
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

  portfolio.liquidate()
  portfolio.create_equity_curve()
  portfolio.equity_curve.to_csv("equity_curve.csv")


@app.command()
def plot_results():
  """
  Plot the results of the last backtest.
  """
  typer.echo("Plotting results...")
  # --- TO BE IMPLEMENTED ---


if __name__ == "__main__":
  app()
