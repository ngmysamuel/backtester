import typer
from typing import Optional, List
from backtester.data.csv_data_handler import CSVDataHandler
import collections
from backtester.strategies.strategy import Strategy
import yaml
import importlib.resources
import importlib

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
        strategy: Optional[str] = "buy_and_hold_simple"
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

  StrategyClass = load_class(config["strategies"][strategy]["name"])
  additional_params = config["strategies"][strategy].get("additional_parameters", {})

  event_queue = collections.deque()
  data_handler = CSVDataHandler(event_queue, data_dir, symbol_list)
  strategy_instance = StrategyClass(event_queue, data_handler, **additional_params)
  
  while data_handler.continue_backtest:
    data_handler.update_bars()
    # Process events from the event queue
    while event_queue:
      event = event_queue.popleft()
      # Handle the event (e.g., generate signals, execute orders, etc.)
      if event.type == "MARKET":
         strategy_instance.generate_signals(event)
      elif event.type == "SIGNAL":
         typer.echo(f"Signal generated: {event.symbol} {event.signal_type} at {event.datetime}")


@app.command()
def plot_results():
  """
  Plot the results of the last backtest.
  """
  typer.echo("Plotting results...")
  # --- TO BE IMPLEMENTED ---


if __name__ == "__main__":
  app()
