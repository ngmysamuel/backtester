from backtester.portfolios.portfolio import Portfolio
from collections import deque
from backtester.data.data_handler import DataHandler
from backtester.enums.direction_type import DirectionType
from backtester.enums.order_type import OrderType
from backtester.events.order_event import OrderEvent
import pandas as pd

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
    maintenance_margin: float = 0.3
  ):
    """
    Initializes the NaivePortfolio with initial capital, a list of symbols, an event queue, and allocation percentage.

    Parameters:
    data_handler (DataHandler): The data handler object to fetch market data.
    initial_capital (float): The starting capital for the portfolio.
    symbol_list (list): List of ticker symbols to include in the portfolio.
    events (deque): The event queue to communicate with other components.
    start_date (float): The starting timestamp for the portfolio.
    allocation (float): The percentage of the portfolio that an asset is maximally allowed to take (default is 1).
    borrow_cost (float): The annualized interest rate for borrowing stocks to short sell (default is 0.01, i.e., 1%).
    maintenance_margin (float): The minimum equity percentage required to maintain a short position (default is 0.3, i.e., 30%).
    """
    self.data_handler = data_handler
    self.initial_capital = initial_capital
    self.symbol_list = symbol_list
    self.events = events
    self.current_date = pd.to_datetime(start_date, unit='s')
    self.allocation = allocation
    self.borrow_cost = borrow_cost
    self.maintenance_margin = maintenance_margin

    self.order_queue = deque
    self.position_size = 100  # to be derived

    self.current_holdings = {sym: 0.0 for sym in self.symbol_list} | {sym + " position": 0 for sym in self.symbol_list}
    self.current_holdings["cash"] = initial_capital
    self.current_holdings["total"] = initial_capital
    self.current_holdings["commissions"] = 0.0
    self.current_holdings["timestamp"] = start_date
    self.current_holdings["position"] = 0
    self.historical_holdings = [self.current_holdings.copy()]

  def _calc_short_borrow_costs(self):
    """
    Calculate the borrow costs for all short positions in the portfolio.
    This method will be called daily to update the borrow costs.
    """
    for sym in self.symbol_list:
      if self.current_holdings[f"{sym} position"] < 0: # only apply borrow cost to short positions
        bar = self.data_handler.get_latest_bars(sym)[0]
        daily_borrow_cost = abs(self.current_holdings[f"{sym} position"]) * bar.open * (self.borrow_cost / 252) # assuming 252 trading days in a year
        self.current_holdings["cash"] -= daily_borrow_cost
        self.current_holdings["total"] -= daily_borrow_cost
        self.current_holdings["borrow_costs"] += daily_borrow_cost


  def on_market(self, event):
    """
    Updates the portfolio's positions and holdings based on the latest market data.
    This method should be called whenever a new market event is received.
    """
    ticker = event.ticker
    timestamp = event.timestamp
    event_datetime = pd.to_datetime(event.timestamp, unit='s')

    if event_datetime - self.current_date >= pd.Timedelta("1D"):
      self._calc_short_borrow_costs()
      self.current_date = event_datetime

    old_holding = self.current_holdings[ticker]
    if self.current_holdings["timestamp"] != timestamp:
      self.current_holdings = self.current_holdings.copy()
      self.current_holdings["timestamp"] = timestamp
      self.current_holdings["order"] = ""
      self.current_holdings["commissions"] = 0.0
      self.current_holdings["borrow_costs"] = 0.0
      self.historical_holdings.append(self.current_holdings)
    latest_bar = self.data_handler.get_latest_bars(ticker)[0]
    self.current_holdings[ticker] = self.current_positions[ticker] * latest_bar.close # use closing price to evaluate portfolio value
    self.current_holdings["total"] += self.current_holdings[ticker] - old_holding

  def on_fill(self, event):
    bar = self.data_handler.get_latest_bars(event.ticker)[0]
    self.current_holdings[f"{event.ticker} position"] += event.direction.value * event.quantity
    self.current_holdings[event.ticker] = self.current_holdings[f"{event.ticker} position"] * bar.close # use closing price to evaluate portfolio value
    self.current_holdings["cash"] -= event.fill_cost + event.commission
    self.current_holdings["total"] -= event.commission
    self.current_holdings["commissions"] += event.commission
    self.current_holdings["order"] += f" | {event.direction.name} {event.quantity} {event.ticker}"

  def on_signal(self, event):
    order = None
    ticker = event.ticker
    order_type = OrderType.MKT
    cur_quantity = self.current_positions[ticker]
    quantity = self.position_size * event.strength
 
    if event.signal_type.value == -1: # SHORT
      if self.current_holdings[ticker] > 0: # currently LONG, need to exit first
        quantity += self.current_holdings[ticker]
      order = OrderEvent(DirectionType(-1), ticker, order_type, quantity, event.timestamp)
    elif event.signal_type.value == 1: # LONG
      if self.current_holdings[ticker] < 0: # currently SHORT, need to exit first
        quantity += abs(self.current_holdings[ticker])
      order = OrderEvent(DirectionType(1), ticker, order_type, quantity, event.timestamp)
    else:
      if cur_quantity > 0: # EXIT a long position
        order = OrderEvent(DirectionType(-1), ticker, order_type, cur_quantity, event.timestamp)
      elif cur_quantity < 0: # EXIT a short position
        order = OrderEvent(DirectionType(1), ticker, order_type, cur_quantity + self.position_size, event.timestamp)

    if order:
      self.events.append(order)
      self.current_holdings["order"] = order.direction


  def create_equity_curve(self):
    curve = pd.DataFrame(self.historical_holdings)
    curve.set_index("timestamp", inplace=True)
    curve["returns"] = curve["total"].pct_change()
    curve["equity_curve"] = (1.0 + curve["returns"]).cumprod()
    self.equity_curve = curve