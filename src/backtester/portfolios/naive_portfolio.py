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
  ):
    """
    Initializes the NaivePortfolio with initial capital, a list of symbols, an event queue, and allocation percentage.

    Parameters:
    data_handler (DataHandler): The data handler object to fetch market data.
    initial_capital (float): The starting capital for the portfolio.
    symbol_list (list): List of ticker symbols to include in the portfolio.
    events (deque): The event queue to communicate with other components.
    start_date (float): The starting timestamp for the portfolio.
    allocation (float): The fixed percentage of the portfolio to allocate to each asset (default is 1).
    """
    self.data_handler = data_handler
    self.initial_capital = initial_capital
    self.symbol_list = symbol_list
    self.events = events
    self.allocation = allocation

    self.order_queue = deque
    self.position_size = 100  # to be derived

    self.current_positions = {sym: 0 for sym in self.symbol_list}
    self.current_positions["timestamp"] = start_date
    self.historical_positions = [self.current_positions.copy()]

    self.current_holdings = {sym: 0.0 for sym in self.symbol_list}
    self.current_holdings["cash"] = initial_capital
    self.current_holdings["total"] = initial_capital
    self.current_holdings["commissions"] = 0.0
    self.current_holdings["timestamp"] = start_date
    self.historical_holdings = [self.current_holdings.copy()]

  def on_market(self, event):
    """
    Updates the portfolio's positions and holdings based on the latest market data.
    This method should be called whenever a new market event is received.
    """
    ticker = event.ticker
    # Update holdings
    timestamp = event.timestamp
    old_holding = self.current_holdings[ticker]
    if self.current_holdings["timestamp"] != timestamp:
      self.current_holdings = self.current_holdings.copy()
      self.current_holdings["timestamp"] = timestamp
      self.historical_holdings.append(self.current_holdings)
    latest_bar = self.data_handler.get_latest_bars(ticker)[0]
    self.current_holdings[ticker] = self.current_positions[ticker] * latest_bar.close # use closing price to evaluate portfolio value
    self.current_holdings["total"] += self.current_holdings[ticker] - old_holding

  def on_fill(self, event):
    direction = event.direction.value
    self.current_positions[event.ticker] += direction * event.quantity
    self.current_holdings[event.ticker] += event.fill_cost
    self.current_holdings["cash"] -= event.fill_cost

  def on_signal(self, event):
    order = None
    ticker = event.ticker
    order_type = OrderType.MKT
    cur_quantity = self.current_positions[ticker]
    quantity = self.position_size * event.strength
 
    if event.signal_type.value == -1: # SHORT
      order = OrderEvent(DirectionType(-1), ticker, order_type, quantity)
    elif event.signal_type.value == 1 and self.current_holdings[ticker] < self.current_holdings["total"] * self.allocation: # LONG
      order = OrderEvent(DirectionType(1), ticker, order_type, quantity)
    else:
      if cur_quantity > 0: # EXIT a long position
        order = OrderEvent(DirectionType(-1), ticker, order_type, abs(cur_quantity))
      elif cur_quantity < 0: # EXIT a short position
        order = OrderEvent(DirectionType(1), ticker, order_type, abs(cur_quantity))

    if order:
      self.events.append(order)


  def create_equity_curve(self):
    curve = pd.DataFrame(self.historical_holdings)
    curve.set_index("timestamp", inplace=True)
    curve["returns"] = curve["total"].pct_change()
    curve["equity_curve"] = (1.0 + curve["returns"]).cumprod()
    self.equity_curve = curve