from collections import deque
from backtester.events.fill_event import FillEvent
import pandas as pd
import datetime

class ExecutionHandler:
  def __init__(self, events, data_handler, exch_closing, interval="1d"):
    self.events = events
    self.data_handler = data_handler
    self.exch_closing = exch_closing
    self.interval = interval
    self.order_queue = deque()
    
  def on_market(self, event):
    """
    On a MarketEvent, check which order can be executed. All orders, if can be filled, will be filled entirely.
    """
    while self.order_queue:
      order = self.order_queue.popleft()
      bar = self.data_handler.get_latest_bars(order.ticker)[0]
      current_time = bar.Index.timestamp()
      if order.timestamp >= current_time:
        self.order_queue.appendleft(order)  # put it back and wait for next market event
        return
      if order.order_type.name == "MKT":
        fill_cost = order.direction.value * order.quantity * bar.open
      elif order.order_type.name == "MOC" and bar.Index + pd.Timedelta(self.interval) >= bar.Index.replace(hour=int(self.exch_closing.split(":")[0]),minute=int(self.exch_closing.split(":")[1])):
        fill_cost = order.direction.value * order.quantity * bar.close
      fill_event = FillEvent(current_time, order.ticker, "ARCA", order.quantity, order.direction, fill_cost)
      self.events.append(fill_event)

  def on_order(self, event):
    """
    Processes an OrderEvent to execute trades.
    """
    self.order_queue.append(event)