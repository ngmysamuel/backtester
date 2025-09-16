import typer
from typing import Optional
from data.csv_data_hanlder import CSVDataHandler
import collections

app = typer.Typer()


@app.command()
def run(strategy: Optional[str] = None,
        start_date: Optional[str] = None,
        data_dir: Optional[str] = None,
        symbol_list: Optional[str] = None
      ):
  """
  Run the backtester with a given strategy and date range.
  args:
      strategy (str): Path to the strategy file.
      start_date (str): Start date in YYYY-MM-DD format.
  """
  typer.echo(f"Running backtest for strategy: {strategy}")
  typer.echo(f"Starting from: {start_date}")
  # --- TO BE IMPLEMENTED ---
  event_queue = collections.deque()
  data_handler = CSVDataHandler(event_queue, data_dir, symbol_list)  # Placeholder for actual data handler initialization
  while data_handler.continue_backtest:
    data_handler.update_bars()
    # Process events from the event queue
    while event_queue:
      event = event_queue.popleft()
      # Handle the event (e.g., generate signals, execute orders, etc.)


@app.command()
def plot_results():
  """
  Plot the results of the last backtest.
  """
  typer.echo("Plotting results...")
  # --- TO BE IMPLEMENTED ---


if __name__ == "__main__":
  app()
