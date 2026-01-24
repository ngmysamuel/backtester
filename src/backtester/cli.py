import importlib
import importlib.resources
import runpy
import sys
from pathlib import Path
from queue import Queue
from typing import Optional

import pandas as pd
import quantstats as qs
import typer
import yaml
from rich import box
from rich.console import Console
from rich.table import Table

from backtester.execution.simulated_execution_handler import SimulatedExecutionHandler
from backtester.portfolios.naive_portfolio import NaivePortfolio
from backtester.util.bar_manager import BarManager
from backtester.data.news_data_handler import NewsDataHandler

console = Console()
app = typer.Typer()


def load_config(config_path: Optional[str] = None):
    """Loads the configuration from config.yaml."""
    if config_path:
        with open(config_path, "r") as f:
            config = yaml.safe_load(f)
        return config

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
def run(data_dir: Optional["str"] = None, data_source: Optional[str] = "yf", position_calc: Optional[str] = "atr", slippage: Optional[str] = "multi_factor_slippage", strategy: Optional[str] = "moving_average", analyze_sentiment: Optional[bool] = False, risk_manager: Optional[str] = "simple_risk_manager", exception_contd: Optional[int] = 0, config_path: Optional[str] = None, output_path: Optional[str] = ".", start_date: str = None, end_date: str = None, initial_capital: float = None, ticker_list: list[str] = None, benchmark: str = None):
    """
    Run the backtester with a given strategy and date range.
    args:
        data_dir: Directory containing CSV data files.
        data_source: Where the OHLC data comes from
        position_calc: the method to caculcate position size
        slippage (str): the model used to calculate slippage
        strategy: the strategy to backtest; this name should match those found in config.yaml.
        analyze_sentiment: starts up the news api data handler to parse news feeds
        risk_manager: the class used to quantify risk and decide to go ahead with the trade
        exception_contd: 1 or 0
        config_path: Path to a custom config file (optional)
        output_path: Path to save the equity curve CSV (optional, default: equity_curve.csv)
        start_date: optional override to the value given in config
        end_date: optional override to the value given in config
        initial_capital: optional override to the value given in config
        ticker_list: optional override to the value given in config
        benchmark: optional override to the value given in config
    """

    ####################
    # sanity checks on passed in variables
    ####################
    if analyze_sentiment and data_source != "live":
        console.print("[bold red]Unable to analyze sentiment if data-source <> live. Try again with --data-source live[/bold red]")
        return

    ####################
    # load data from yaml config file
    ####################
    config = load_config(config_path)

    backtester_settings = config["backtester_settings"]
    if start_date:
        backtester_settings["start_date"] = start_date
    if end_date:
        backtester_settings["end_date"] = end_date
    if initial_capital:
        backtester_settings["initial_capital"] = initial_capital

    cash_buffer = backtester_settings["cash_buffer"]
    initial_capital = backtester_settings["initial_capital"]
    initial_position_size = backtester_settings["initial_position_size"]
    start_timestamp = pd.to_datetime(start_date or backtester_settings["start_date"], dayfirst=True).timestamp()
    end_timestamp = pd.to_datetime(end_date or backtester_settings["end_date"], dayfirst=True).timestamp()
    base_interval = backtester_settings["base_interval"]
    metrics_interval = backtester_settings["metrics_interval"]
    sentiment_interval = backtester_settings["sentiment_interval"]
    period = backtester_settings["period"]
    exchange_closing_time = backtester_settings["exchange_closing_time"]
    benchmark_ticker = benchmark or backtester_settings["benchmark"]

    # TODO: enhance for multi strategy handling
    strategy_interval = config["strategies"][strategy]["additional_parameters"]["interval"]
    symbol_list = ticker_list or config["strategies"][strategy]["additional_parameters"]["symbol_list"]
    keyword_dict = config["strategies"][strategy]["additional_parameters"].get("keyword_dict", None)
    rounding_list = config["strategies"][strategy]["additional_parameters"]["rounding_list"]

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
    typer_tbl.add_row("Initial Position Size", str(initial_position_size))
    typer_tbl.add_row("Start Date", start_date or backtester_settings["start_date"])
    typer_tbl.add_row("End Date", end_date or backtester_settings["end_date"])
    typer_tbl.add_row("Base Interval", base_interval)
    typer_tbl.add_row("Metrics Interval", metrics_interval)
    typer_tbl.add_row("Strategy Interval", strategy_interval)
    typer_tbl.add_row("Period (only for live)", period)
    typer_tbl.add_row("Analyzing Sentiments?", str(analyze_sentiment))
    console.print(typer_tbl)

    ####################
    # set up helper classes / vars
    ####################
    event_queue = Queue()

    DataHandlerClass = load_class(config["data_handler"][data_source]["name"])
    data_handler_settings = backtester_settings | {"symbol_list": symbol_list + [benchmark_ticker], "data_dir": data_dir}
    data_handler = DataHandlerClass(event_queue, **data_handler_settings)

    news_data_handler = None
    if analyze_sentiment:
        data_handler_settings = config["data_handler"]["news"].get("additional_parameters", {})
        data_handler_settings = data_handler_settings | backtester_settings | {"symbol_list": symbol_list, "keyword_dict": keyword_dict, "sentiment_interval": sentiment_interval}
        news_data_handler = NewsDataHandler(event_queue, **data_handler_settings)

    bar_manager = BarManager(data_handler, news_data_handler, base_interval)

    PositionSizerClass = load_class(config["position_sizer"][position_calc]["name"])
    position_sizer_settings = config["position_sizer"][position_calc].get("additional_parameters", None)
    position_sizer = PositionSizerClass(position_sizer_settings, symbol_list)
    for ticker in symbol_list:
        bar_manager.subscribe(strategy_interval, ticker, position_sizer)

    StrategyClass = load_class(config["strategies"][strategy]["name"])
    strategy_settings = config["strategies"][strategy].get("additional_parameters", {})
    if strategy_settings and ticker_list:
        strategy_settings["symbol_list"] = ticker_list
    strategy_instance = StrategyClass(event_queue, strategy, **strategy_settings)
    for ticker in symbol_list:
        bar_manager.subscribe(strategy_interval, ticker, strategy_instance)

    SlippageClass = load_class(config["slippage"][slippage]["name"])
    slippage_settings = config["slippage"][slippage].get("additional_parameters", None)
    slippage_model = SlippageClass(slippage_settings)
    for ticker in symbol_list:
        bar_manager.subscribe(strategy_interval, ticker, slippage_model)

    RiskManagerClass = load_class(config["risk_manager"][risk_manager]["name"])
    risk_manager_settings = config["risk_manager"][risk_manager].get("additional_parameters", None)
    risk_manager_instance = RiskManagerClass(risk_manager_settings)

    portfolio = NaivePortfolio(cash_buffer, initial_capital, initial_position_size, symbol_list, rounding_list, event_queue, start_timestamp, base_interval, metrics_interval, position_sizer, strategy, risk_manager_instance)
    for ticker in symbol_list:
        bar_manager.subscribe(base_interval, ticker, portfolio)

    execution_handler = SimulatedExecutionHandler(event_queue, data_handler, slippage_model)

    mkt_close = False

    ####################
    # start up the main loop
    #   the base interval acts as the hearbeat of the whole system
    #   strategy intervals will take its cue from the base interval
    ####################

    while data_handler.continue_backtest or not event_queue.empty():  # continue_backtest - to be made thread safe?
        data_handler.update_bars()
        # Process events from the event queue (e.g., generate signals, execute orders, etc.)
        while not event_queue.empty():
            event = event_queue.get(block=False)
            if event.type == "MARKET":
                bar_manager.on_heartbeat(event)
                mkt_close = event.is_eod
                execution_handler.on_market(event, mkt_close)  # check if any orders can be filled, if so, it will update the portfolio via a FILL event
            elif event.type == "SIGNAL":
                if event.ticker != benchmark_ticker:  # we skip any signals generated for the benchmark
                    portfolio.on_signal(event)
            elif event.type == "ORDER":
                execution_handler.on_order(event)
            elif event.type == "FILL":
                portfolio.on_fill(event)
        if mkt_close:
            portfolio.end_of_day()  # deduct borrow costs and calculate margin
            mkt_close = False

    print("Backtest is complete, outputting results now...")
    ####################
    # metrics and results
    ####################
    portfolio.create_equity_curve()
    output_path = Path(output_path)
    output_file = str(output_path.joinpath("equity_curve.csv"))
    print(f"Saving to {output_file}")
    portfolio.equity_curve.to_csv(output_file)

    benchmark_data = data_handler.symbol_raw_data[benchmark_ticker]
    benchmark_returns = benchmark_data["close"].pct_change().fillna(0.0)
    benchmark_returns.name = benchmark_ticker

    # TODO: if equity curve values are all the same, this will fail
    qs.reports.html(portfolio.equity_curve["returns"], benchmark=benchmark_returns, output=str(output_path.joinpath("strategy_report.html")), title=strategy, match_dates=False)


@app.command()
def dashboard(is_docker: int = 0):
    """
    Plot the results of the last backtest.
    """
    config = load_config()
    interval = config["backtester_settings"]["metrics_interval"]
    streamlit_script_path = Path("src/backtester/metrics/dashboard/streamlit_app.py").resolve()
    console.print(f"Loading [underline]{streamlit_script_path}[/underline]")
    sys.argv = ["streamlit", "run", str(streamlit_script_path), "--global.disableWidgetStateDuplicationWarning", "true", f" -- --interval {interval}", f" -- --is_docker {is_docker}"]  # for more arguments, add ', " -- --what ee"' to the end
    runpy.run_module("streamlit", run_name="__main__")


if __name__ == "__main__":
    app()
