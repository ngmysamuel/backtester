from backtester.portfolios.portfolio import Portfolio
from collections import deque
from backtester.data.data_handler import DataHandler
from backtester.enums.direction_type import DirectionType
from backtester.enums.order_type import OrderType
from backtester.events.order_event import OrderEvent
import pandas as pd
import numpy as np
import collections
from backtester.exceptions.negative_cash_exception import NegativeCashException
from copy import deepcopy
from backtester.metrics.performance import calc_sharpe_ratio, calc_drawdowns

class NaivePortfolio(Portfolio):
  """
  A naive portfolio implementation.
  This class handles things like Risk Management, Position Sizing, and Portfolio Allocation / Valuation (albeit not handle / naively).
  """

  def __init__(
    self,
    data_handler: DataHandler,
    initial_capital: float,
    symbol_list: list[str],
    events: deque,
    start_date: float,
    interval: str,
    allocation: float = 1,
    borrow_cost: float = 0.01,
    maintenance_margin: float = 0.3,
    risk_per_trade: float = 0.01,
    atr_period: int = 14,
    atr_multiplier: int = 2
  ):
    """
    Initializes the NaivePortfolio with initial capital, a list of symbols, an event queue, and allocation percentage.

    args:
      data_handler (DataHandler): The data handler object to fetch market data.
      initial_capital (float): The starting capital for the portfolio.
      symbol_list (list): List of ticker symbols to include in the portfolio.
      events (deque): The event queue to communicate with other components.
      start_date (float): The starting timestamp for the portfolio.
      interval (str): 
      allocation (float): The percentage of the portfolio that an asset is maximally allowed to take (default is 1).
      borrow_cost (float): The annualized interest rate for borrowing stocks to short sell (default is 0.01, i.e., 1%).
      maintenance_margin (float): The minimum equity percentage required to maintain a short position (default is 0.2, i.e., 20%).

    Attributes:
      daily_borrow_rate: the daily interest rate for borrowing stocks to short sell
      margin_holdings: tracks the margin held for each symbol when shorting
      current_holdings: polarity of values indicate a short (<0) or long (>0) position
    """
    self.data_handler = data_handler
    self.initial_capital = initial_capital
    self.symbol_list = symbol_list
    self.events = events
    self.start_date = start_date
    self.interval = interval
    self.allocation = allocation
    self.daily_borrow_rate = borrow_cost / 252 # assuming 252 trading days in a year
    self.maintenance_margin = maintenance_margin
    self.risk_per_trade = risk_per_trade
    self.atr_period = atr_period
    self.atr_multiplier = atr_multiplier

    self.margin_holdings = collections.defaultdict(int)
    self.position_size = {sym: 100 for sym in self.symbol_list}  # to be derived
    self.historical_atr = {sym: [] for sym in self.symbol_list}

    self.current_holdings = {sym: {"position": 0, "value": 0.0} for sym in self.symbol_list}
    self.current_holdings["cash"] = initial_capital
    self.current_holdings["total"] = initial_capital
    self.current_holdings["commissions"] = 0.0
    self.current_holdings["timestamp"] = start_date
    self.current_holdings["borrow_costs"] = 0.0
    self.current_holdings["order"] = ""
    self.historical_holdings = [self.current_holdings.copy()]

  def on_market(self, event):
    """
    Updates the portfolio's positions and holdings based on the latest market data.
    This method is called whenever a new market event is received.
    """
    self.current_holdings = deepcopy(self.current_holdings)
    self.current_holdings["commissions"] = 0.0
    self.current_holdings["timestamp"] = event.timestamp
    self.current_holdings["borrow_costs"] = 0.0
    self.current_holdings["order"] = ""
    self.historical_holdings.append(self.current_holdings)

    if self.current_holdings["cash"] < 0:
      raise NegativeCashException(self.current_holdings["cash"])


  def on_signal(self, event):
    order = None
    ticker = event.ticker
    order_type = OrderType.MKT
    cur_quantity = self.current_holdings[ticker]["position"]

    atr_list = self.historical_atr[ticker]
    if len(atr_list) > 0: # check for ATR > 0 to prevent ZeroDivisionError, else, reuse previous position size
      atr = self.historical_atr[ticker][-1]
      if atr:
        capital_to_risk = min(self.current_holdings["cash"], self.risk_per_trade * self.current_holdings["total"])
        self.position_size[ticker] = capital_to_risk // (atr * self.atr_multiplier)

    to_be_quantity = self.position_size[ticker] * event.strength
 
    if event.signal_type.value == -1: # SHORT
      if cur_quantity > 0: # currently LONG, need to exit first
        to_be_quantity += cur_quantity
      order = OrderEvent(DirectionType(-1), ticker, order_type, to_be_quantity, event.timestamp)
    elif event.signal_type.value == 1: # LONG
      if cur_quantity < 0: # currently SHORT, need to exit first
        to_be_quantity += abs(cur_quantity)
      order = OrderEvent(DirectionType(1), ticker, order_type, to_be_quantity, event.timestamp)
    else: # EXIT
      if cur_quantity > 0: # EXIT a long position
        order = OrderEvent(DirectionType(-1), ticker, order_type, cur_quantity, event.timestamp)
      elif cur_quantity < 0: # EXIT a short position
        order = OrderEvent(DirectionType(1), ticker, order_type, abs(cur_quantity), event.timestamp)

    if order:
      self.events.append(order)

  def on_fill(self, event):
    """
    Updates the portfolio's positions and holdings based on a FillEvent.
    """
    bar = self.data_handler.get_latest_bars(event.ticker)[0]
    initial_holding = self.current_holdings[event.ticker]["value"]
    self.current_holdings[event.ticker]["position"] += event.direction.value * event.quantity
    self.current_holdings[event.ticker]["value"] = self.current_holdings[event.ticker]["position"] * bar.close # use closing price to evaluate portfolio value
    self.current_holdings["total"] += (self.current_holdings[event.ticker]["value"] - initial_holding - event.commission) # subtract a negative number makes a plus
    self.current_holdings["cash"] += -1 * event.direction.value * event.fill_cost - event.commission # less the actual cost to buy/sell the stock, 
    self.current_holdings["commissions"] += event.commission
    self.current_holdings["order"] += f" | {event.direction.name} {event.quantity} {event.ticker}"

  def end_of_day(self):
    """
    The end of the trading day - perform mark to market activities like margin calculation and borrow costs
    """
    self.current_holdings["total"] = 0 # recalculate
    for ticker in self.symbol_list:
      latest_bar = self.data_handler.get_latest_bars(ticker)[0]
      self.current_holdings[ticker]["value"] = self.current_holdings[ticker]["position"] * latest_bar.close
      self.current_holdings["total"] += self.current_holdings[ticker]["value"] # add value of current position
      if self.current_holdings[ticker]["position"] < 0: # nett SHORT position
        # MARGIN
        margin_diff = self.margin_holdings[ticker] + (self.current_holdings[ticker]["value"]) * (1 + self.maintenance_margin) # margin change
        self.current_holdings["cash"] += margin_diff # cash frozen for margin, reduction if margin_diff is -ve
        self.margin_holdings[ticker] -= margin_diff
        self.current_holdings["total"] += self.margin_holdings[ticker] # total portfolio value is inclusive of margin
        # BORROW COSTS
        daily_borrow_cost = abs(self.current_holdings[ticker]["value"]) * self.daily_borrow_rate
        self.current_holdings["cash"] -= daily_borrow_cost
        self.current_holdings["borrow_costs"] += daily_borrow_cost
      else: # nett LONG position
        self.current_holdings["cash"] += self.margin_holdings[ticker] # release any margin being held
        self.margin_holdings[ticker] = 0 # reset margin
    self.current_holdings["total"] += self.current_holdings["cash"]
    self.current_holdings["margin"] = self.margin_holdings.copy()
  
  def end_of_interval(self):
    """
    The end of a trading interval e.g. 5mins, 1day - perform tasks that can only take place only take place at the END of the current interval
    """
    for ticker in self.symbol_list:
      atr = self._calc_atr(ticker)
      if atr:
        self.historical_atr[ticker].append(atr)


  def liquidate(self):
    self.current_holdings = deepcopy(self.current_holdings)
    self.current_holdings["timestamp"] = pd.to_datetime(self.current_holdings["timestamp"], unit="s") + pd.Timedelta(self.interval)
    self.current_holdings["timestamp"] = self.current_holdings["timestamp"].timestamp()
    self.current_holdings["commissions"] = 0.0
    self.current_holdings["borrow_costs"] = 0.0
    self.current_holdings["order"] = ""
    self.historical_holdings.append(self.current_holdings)
    for ticker in self.symbol_list:
      latest_bar = self.data_handler.get_latest_bars(ticker)[0]
      if self.current_holdings[ticker]["position"] < 0: # nett SHORT position
        self.current_holdings["cash"] += self.margin_holdings[ticker] # release any margin being held
      self.current_holdings["cash"] += self.current_holdings[ticker]["position"] * latest_bar.close
      self.current_holdings[ticker]["position"] = 0
      self.current_holdings[ticker]["value"] = 0
      self.current_holdings["margin"][ticker] = 0
    self.current_holdings["total"] = self.current_holdings["cash"]


  def _calc_atr(self, ticker): # # Use Wilder's Smoothing 
    if len(self.historical_atr[ticker]) < 1: # initialization of average true range uses simple arithmetic mean
      bar_data = self.data_handler.get_latest_bars(ticker, self.atr_period + 1)
      if len(bar_data) < self.atr_period + 1:
        return

      bar_data = pd.DataFrame(bar_data)
      bar_data["h-l"] = bar_data["high"] - bar_data["low"]
      bar_data["h-prev"] = (bar_data["high"] - bar_data["close"].shift(periods=1)).abs()
      bar_data["l-prev"] = (bar_data["low"] - bar_data["close"].shift(periods=1)).abs()
      
      tr = np.nanmax(bar_data[["h-l","h-prev","l-prev"]], axis=1)
      
      atr = tr.mean()
    else:
      bar_data = self.data_handler.get_latest_bars(ticker, 2)
      bar_data = pd.DataFrame(bar_data)
      bar_data["h-l"] = bar_data["high"] - bar_data["low"]
      bar_data["h-prev"] = (bar_data["high"] - bar_data["close"].shift(periods=1)).abs()
      bar_data["l-prev"] = (bar_data["low"] - bar_data["close"].shift(periods=1)).abs()

      tr = np.nanmax(bar_data[["h-l","h-prev","l-prev"]], axis=1)[-1]
      atr = 1/self.atr_period * tr + (1- 1/self.atr_period) * self.historical_atr[ticker][-1]

    return atr 


  def create_equity_curve(self):
    curve = pd.DataFrame(self.historical_holdings)
    curve["timestamp"] = pd.to_datetime(curve["timestamp"], unit="s")
    curve.set_index("timestamp", inplace=True)
    curve["returns"] = curve["total"].pct_change()
    curve["equity_curve"] = (1.0 + curve["returns"]).cumprod()
    self.equity_curve = curve


  def create_statistics(self):
    sharpe_ratio = calc_sharpe_ratio(self.equity_curve["returns"])
    max_dd, dd_duration = calc_drawdowns(self.equity_curve["equity_curve"])
    return {
      "sharpe": sharpe_ratio,
      "max_dd": max_dd,
      "dd_duration": dd_duration
    }