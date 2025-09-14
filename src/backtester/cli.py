import typer
from typing import Optional

app = typer.Typer()


@app.command()
def run(strategy: Optional[str] = None, start_date: Optional[str] = None):
  """
  Run the backtester with a given strategy and date range.
  args:
      strategy (str): Path to the strategy file.
      start_date (str): Start date in YYYY-MM-DD format.
  """
  typer.echo(f"Running backtest for strategy: {strategy}")
  typer.echo(f"Starting from: {start_date}")
  # --- TO BE IMPLEMENTED ---


@app.command()
def plot_results():
  """
  Plot the results of the last backtest.
  """
  typer.echo("Plotting results...")
  # --- TO BE IMPLEMENTED ---


if __name__ == "__main__":
  app()
