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
import math

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
      allocation (float): The percentage of the portfolio that an asset is maximally allowed to take (default is 1).
      borrow_cost (float): The annualized interest rate for borrowing stocks to short sell (default is 0.01, i.e., 1%).
      maintenance_margin (float): The minimum equity percentage required to maintain a short position (default is 0.3, i.e., 30%).

    Attributes:
      daily_borrow_rate: the daily interest rate for borrowing stocks to short sell
      margin_holdings: tracks the margin held for each symbol when shorting
      order_queue: a queue to hold orders before execution
      current_holdings: polarity of values indicate a short (<0) or long (>0) position
    """
    self.data_handler = data_handler
    self.initial_capital = initial_capital
    self.symbol_list = symbol_list
    self.events = events
    self.allocation = allocation
    self.daily_borrow_rate = borrow_cost / 252 # assuming 252 trading days in a year
    self.maintenance_margin = maintenance_margin
    self.risk_per_trade = risk_per_trade
    self.atr_period = atr_period
    self.atr_multiplier - atr_multiplier

    self.margin_holdings = collections.defaultdict(int)
    self.order_queue = deque
    self.position_size = 100  # to be derived

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
    self.current_holdings = self.current_holdings.copy()
    self.current_holdings["commissions"] = 0.0
    self.current_holdings["timestamp"] = event.timestamp
    self.current_holdings["borrow_costs"] = 0.0
    self.current_holdings["order"] = ""
    self.historical_holdings.append(self.current_holdings)

    atr = self._calc_atr()
    if atr:
      capital_to_risk = min(self.current_holdings["cash"], self.risk_per_trade * self.current_holdings["total"])
      self.position_size = math.floor(capital_to_risk * atr)

    if self.current_holdings["cash"] < 0:
      raise NegativeCashException(self.current_holdings["cash"])


  def on_signal(self, event):
    order = None
    ticker = event.ticker
    order_type = OrderType.MKT
    cur_quantity = self.current_positions[ticker]
    to_be_quantity = self.position_size * event.strength
 
    if event.signal_type.value == -1: # SHORT
      if self.current_holdings[ticker] > 0: # currently LONG, need to exit first
        to_be_quantity += self.current_holdings[ticker]["position"]
      order = OrderEvent(DirectionType(-1), ticker, order_type, to_be_quantity, event.timestamp)
    elif event.signal_type.value == 1: # LONG
      if self.current_holdings[ticker] < 0: # currently SHORT, need to exit first
        to_be_quantity += abs(self.current_holdings[ticker]["position"])
      order = OrderEvent(DirectionType(1), ticker, order_type, to_be_quantity, event.timestamp)
    else: # EXIT
      if cur_quantity > 0: # EXIT a long position
        order = OrderEvent(DirectionType(-1), ticker, order_type, cur_quantity, event.timestamp)
      elif cur_quantity < 0: # EXIT a short position
        order = OrderEvent(DirectionType(1), ticker, order_type, cur_quantity, event.timestamp)

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
    self.current_holdings["total"] += (self.current_holdings[event.ticker] - initial_holding - event.commission) # subtract a negative number makes a plus
    self.current_holdings["cash"] += -1 * event.direction.value * event.fill_cost - event.commission # less the actual cost to buy/sell the stock, 
    self.current_holdings["commissions"] += event.commission
    self.current_holdings["order"] += f" | {event.direction.name} {event.quantity} {event.ticker}"

  def end_of_day(self):
    self.current_holdings["total"] = 0 # recalculate
    for ticker in self.symbol_list:
      latest_bar = self.data_handler.get_latest_bars(ticker)[0]
      self.current_holdings[ticker]["value"] = self.current_holdings[ticker]["position"] * latest_bar.close
      if self.current_holdings[ticker]["position"] < 0: # nett SHORT position
        # MARGIN
        margin_diff = self.margin_holdings[ticker] - (abs(self.current_holdings[ticker]["value"]) * (1+self.maintenance_margin)) # margin change
        self.current_holdings["cash"] += margin_diff # cash frozen for margin, reduction if margin_diff is -ve
        # BORROW COSTS
        daily_borrow_cost = self.current_holdings[ticker]["value"] * self.daily_borrow_rate
        self.current_holdings["cash"] -= daily_borrow_cost
        self.current_holdings["total"] += (self.current_holdings[ticker]["value"] - daily_borrow_cost)
        self.current_holdings["borrow_costs"] += daily_borrow_cost
      else: # nett LONG position
        self.current_holdings["cash"] += self.margin_holdings[ticker] # release any margin being held
        self.margin_holdings[ticker] = 0 # reset margin
        self.current_holdings["total"] += self.current_holdings[ticker]["value"]

  def _calc_atr(self):
    atr_data = self.data_handler.get_latest_bars(self.atr_period+1)
    if atr_data.shape[0] < self.atr_period + 1:
      return
    atr_data = atr_data.iloc[:-1] # do not use future dated information
    atr_data["h-l"] = atr_data["high"] - atr_data["low"]
    atr_data["h-prev"] = atr_data["high"] - atr_data["close"].shift(periods=1) 
    atr_data["l-prev"] = atr_data["low"] - atr_data["close"].shift(periods=1) 
    atr_data["tr"] = np.max(atr_data["h-l"], atr_data["h-prev"], atr_data["l-prev"])
    return atr_data["tr"].mean()

  def create_equity_curve(self):
    curve = pd.DataFrame(self.historical_holdings)
    curve.set_index("timestamp", inplace=True)
    curve["returns"] = curve["total"].pct_change()
    curve["equity_curve"] = (1.0 + curve["returns"]).cumprod()
    self.equity_curve = curve