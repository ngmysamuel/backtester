import typer
from typing import Optional, List
from backtester.data.csv_data_handler import CSVDataHandler
import collections

app = typer.Typer()


@app.command()
def run(data_dir: str,
        symbol_list: List[str],
        strategy: Optional[str] = None,
        start_date: Optional[str] = None
      ):
  """
  Run the backtester with a given strategy and date range.
  args:
      data_dir (str): Directory containing CSV data files.
      symbol_list (List[str]): List of ticker symbols to include in the backtest.
      strategy (str): Path to the strategy file.
      start_date (str): Start date in YYYY-MM-DD format.
  """
  typer.echo(f"Data directory: {data_dir}")
  typer.echo(f"Symbols: {symbol_list}")
  typer.echo(f"Running backtest for strategy: {strategy}")
  typer.echo(f"Starting from: {start_date}")

  event_queue = collections.deque()
  data_handler = CSVDataHandler(event_queue, data_dir, symbol_list)
  while data_handler.continue_backtest:
    data_handler.update_bars()
    # Process events from the event queue
    while event_queue:
      event = event_queue.popleft()
      # Handle the event (e.g., generate signals, execute orders, etc.)
      if event.type == "MARKET":
         # For demonstration, just print the event
        print(f"Processing event: {event.type}. Ticker: {getattr(event, 'ticker', 'N/A')}")


@app.command()
def plot_results():
  """
  Plot the results of the last backtest.
  """
  typer.echo("Plotting results...")
  # --- TO BE IMPLEMENTED ---


if __name__ == "__main__":
  app()
