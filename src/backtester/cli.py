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
from rich import box
from rich.console import Console
from rich.table import Table

from backtester.exceptions.negative_cash_exception import NegativeCashException
from backtester.execution.simulated_execution_handler import SimulatedExecutionHandler
from backtester.portfolios.naive_portfolio import NaivePortfolio
from backtester.util.util import str_to_seconds

from queue import Queue

console = Console()
app = typer.Typer()


def load_config():
    """Loads the configuration from config.yaml."""
    try:
        # For Python 3.9+
        config_path = importlib.resources.files("backtester") / "config.yaml"
        with config_path.open("r") as f:
            config = yaml.safe_load(f)
        return config
    except (AttributeError, ModuleNotFoundError):
        # Fallback for Python 3.7 and 3.8
        with importlib.resources.open_text("backtester", "config.yaml") as f:
            config = yaml.safe_load(f)
        return config


def load_class(path_to_class: str):
    """Dynamically loads a class from a string."""
    module_path, class_name = path_to_class.rsplit(".", 1)
    m = importlib.import_module(module_path)
    return getattr(m, class_name)


@app.command()
def run(data_dir: Optional["str"], data_source: Optional[str] = "csv", position_calc: Optional[str] = "atr", slippage: Optional[str] = "multi_factor_slippage", strategy: Optional[str] = "buy_and_hold_simple", exception_contd: Optional[int] = 1):
    """
    Run the backtester with a given strategy and date range.
    args:
        data_dir: Directory containing CSV data files.
        data_source: Where the OHLC data comes from
        position_calc: the method to caculcate position size
        slippage (str): the model used to calculate slippage
        strategy: the strategy to backtest; this name should match those found in config.yaml.
        exception_contd: 1 or 0
    """

    ####################
    # load data from yaml config file
    ####################
    config = load_config()

    backtester_settings = config["backtester_settings"]

    symbol_list = backtester_settings["symbol_list"]

    initial_capital = backtester_settings["initial_capital"]
    start_timestamp = pd.to_datetime(backtester_settings["start_date"], dayfirst=True).timestamp()
    end_timestamp = pd.to_datetime(backtester_settings["end_date"], dayfirst=True).timestamp()
    interval = backtester_settings["interval"]
    period = backtester_settings["period"]
    exchange_closing_time = backtester_settings["exchange_closing_time"]
    benchmark_ticker = backtester_settings["benchmark"]

    ####################
    # display loaded configuration
    ####################

    typer_tbl = Table(title="Parameter List", box=box.SQUARE_DOUBLE_HEAD, show_lines=True)
    typer_tbl.add_column("Parameter", style="cyan")
    typer_tbl.add_column("Value")
    typer_tbl.add_row("Data Directory", data_dir)
    typer_tbl.add_row("Data Handler", data_source)
    typer_tbl.add_row("Position Sizer", position_calc)
    typer_tbl.add_row("Slippage", slippage)
    typer_tbl.add_row("Strategy", strategy)
    typer_tbl.add_row("Symbols", ", ".join(symbol_list))
    typer_tbl.add_row("Initial Capital", str(initial_capital))
    typer_tbl.add_row("Start Date", backtester_settings["start_date"])
    typer_tbl.add_row("End Date", backtester_settings["end_date"])
    typer_tbl.add_row("Interval", interval)
    typer_tbl.add_row("Period (only for live)", period)
    console.print(typer_tbl)

    ####################
    # set up helper classes / vars
    ####################

    event_queue = Queue()

    DataHandlerClass = load_class(config["data_handler"][data_source]["name"])
    start_datetime = pd.to_datetime(start_timestamp, unit="s")
    end_datetime = pd.to_datetime(end_timestamp, unit="s")
    if data_source == "yf":
        data_handler = DataHandlerClass(event_queue, start_datetime, end_datetime, symbol_list + [benchmark_ticker], interval, exchange_closing_time)
    elif data_source == "live":
        data_handler = DataHandlerClass(event_queue, symbol_list + [benchmark_ticker], interval, period, exchange_closing_time)
    else:
        data_handler = DataHandlerClass(event_queue, data_dir, start_datetime, end_datetime, symbol_list + [benchmark_ticker], interval, exchange_closing_time)

    PositionSizerClass = load_class(config["position_sizer"][position_calc]["name"])
    position_sizer_settings = config["position_sizer"][position_calc].get("additional_parameters", None)
    position_sizer = PositionSizerClass(position_sizer_settings, symbol_list)

    SlippageClass = load_class(config["slippage"][slippage]["name"])
    slippage_settings = config["slippage"][slippage].get("additional_parameters", None)
    slippage_model = SlippageClass(symbol_list, data_handler, slippage_settings, mode=data_source)

    StrategyClass = load_class(config["strategies"][strategy]["name"])
    additional_params = config["strategies"][strategy].get("additional_parameters", {})
    strategy_instance = StrategyClass(event_queue, data_handler, **additional_params)

    portfolio = NaivePortfolio(data_handler, initial_capital, symbol_list, event_queue, start_timestamp, interval, position_sizer)

    execution_handler = SimulatedExecutionHandler(event_queue, data_handler, slippage_model)

    mkt_close = False
    current_time_interval = None
    interval_seconds = str_to_seconds(interval)

    ####################
    # start up the main loop
    ####################

    while data_handler.continue_backtest:
        data_handler.update_bars()
        # Process events from the event queue (e.g., generate signals, execute orders, etc.)
        while not event_queue.empty():
            event = event_queue.get(block=False)
            if event.type == "MARKET":
                if current_time_interval is None:
                    current_time_interval = event.timestamp
                if event.timestamp >= current_time_interval + interval_seconds:  # the marketEvent timestamp is always the timestamp of the interval start
                    portfolio.end_of_interval()
                    current_time_interval = event.timestamp
                mkt_close = event.is_eod
                try:
                    portfolio.on_market(event)  # update portfolio valuation
                except NegativeCashException as e:
                    if exception_contd:
                        print(e)
                    else:
                        raise e
                slippage_model.on_market()
                execution_handler.on_market(event, mkt_close)  # check if any orders can be filled, if so, it will update the portfolio via a FILL event
                strategy_instance.generate_signals(event)  # generate signals based on market event
            elif event.type == "SIGNAL":
                if event.ticker != benchmark_ticker:  # we skip any isignals generated for the benchmark
                    portfolio.on_signal(event)
            elif event.type == "ORDER":
                execution_handler.on_order(event)
            elif event.type == "FILL":
                portfolio.on_fill(event)
        # portfolio.end_of_interval()
        if mkt_close:
            portfolio.end_of_day()  # deduct borrow costs and calculate margin
            mkt_close = False

    ####################
    # metrics and results
    ####################
    portfolio.create_equity_curve()
    portfolio.equity_curve.to_csv("equity_curve.csv")

    benchmark_data = data_handler.symbol_raw_data[benchmark_ticker]
    benchmark_returns = benchmark_data["close"].pct_change()
    benchmark_returns.name = benchmark_ticker

    # TODO: if equity curve values are all the same, this will fail
    qs.reports.html(portfolio.equity_curve["returns"], benchmark=benchmark_returns, output="strategy_report.html", title=strategy, match_dates=False)


@app.command()
def dashboard():
    """
    Plot the results of the last backtest.
    """
    config = load_config()
    interval = config["backtester_settings"]["interval"]
    streamlit_script_path = Path("src/backtester/metrics/dashboard/streamlit_app.py").resolve()
    console.print(f"Loading [underline]{streamlit_script_path}[/underline]")
    sys.argv = ["streamlit", "run", streamlit_script_path, "--global.disableWidgetStateDuplicationWarning", "true", f" -- --interval {interval}"]  # for more arguments, add ', " -- --what ee"' to the end
    runpy.run_module("streamlit", run_name="__main__")


if __name__ == "__main__":
    app()
