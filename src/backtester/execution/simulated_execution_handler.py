from collections import deque
from backtester.events.fill_event import FillEvent


class SimulatedExecutionHandler:
  """
  SimulatedExecutionHandler simulates the execution of orders as soon as
  they are received, assuming that all orders are filled at the next market
  open price. This class handles both Market and Market-On-Close orders.
  """
  def __init__(self, events, data_handler):
    """
    Initializes the SimulatedExecutionHandler
    args:
        events: the Event Queue
        data_handler: the DataHandler object with current market data
    """
    self.events = events
    self.data_handler = data_handler
    self.order_queue = deque()
    self.mkt_close = False

  def on_market(self, event, mkt_close):
    """
    On a MarketEvent, check which order can be executed. All orders, if can be filled, will be filled entirely.
    """
    self.mkt_close = mkt_close
    while self.order_queue:
      order = self.order_queue.popleft()
      bar = self.data_handler.get_latest_bars(order.ticker)[0]
      current_time = bar.Index.timestamp()
      if order.timestamp >= current_time:
        self.order_queue.appendleft(order)  # put it back and wait for next market event
        return
      if order.order_type.name == "MKT":
        fill_cost = order.quantity * bar.open
      elif order.order_type.name == "MOC" and mkt_close:
        fill_cost = order.quantity * bar.close
      else:
        self.order_queue.append(order)  # put it back and wait for next market event
        continue
      fill_event = FillEvent(
        current_time, order.ticker, "ARCA", order.quantity, order.direction, fill_cost
      )
      self.events.append(fill_event)

  def on_order(self, event):
    """
    Processes an OrderEvent to execute trades.
    """
    self.order_queue.append(event)
