import queue
from collections import deque

import pandas as pd

from backtester.enums.direction_type import DirectionType
from backtester.events.fill_event import FillEvent
from backtester.data.data_handler import DataHandler
from backtester.util.slippage.slippage import Slippage

class SimulatedExecutionHandler:
  """
  SimulatedExecutionHandler simulates the execution of orders as soon as
  they are received, assuming that all orders are filled at the next market
  open price. This class handles both Market and Market-On-Close orders.
  """
  def __init__(self, events: queue.Queue, data_handler: DataHandler, slippage_model: Slippage):
    """
    Initializes the SimulatedExecutionHandler
    args:
        events: the Event Queue
        data_handler: the DataHandler object with current market data
        slippage_model: the model that simulates slippage
    """
    self.events = events
    self.data_handler = data_handler
    self.slippage_model = slippage_model
    self.order_queue = deque()
    self.mkt_close = False

  def on_market(self, event, mkt_close):
    """
    On a MarketEvent, check which order can be executed. All orders, if can be filled, will be filled entirely.
    """
    self.mkt_close = mkt_close
    checked_orders = 0
    orders_to_check = len(self.order_queue)
    while checked_orders < orders_to_check:
      checked_orders += 1
      order = self.order_queue.popleft()
      bar = self.data_handler.get_latest_bars(order.ticker)
      if not bar:
        raise IndexError(f"There is no data for {order.ticker}")
      bar = bar[0]
      current_time = bar.Index.timestamp()
      if order.timestamp >= current_time:
        self.order_queue.appendleft(order)  # put it back and wait for next market event
        return
      slippage = 0.0
      if order.order_type.name == "MOC" and mkt_close:
        fill_cost = order.quantity * bar.close
        unit_cost = bar.close
      else:
        if order.order_type.name == "MKT": # limit, stop-loss orders
          slippage = self.slippage_model.calculate_slippage(order.ticker, pd.to_datetime(order.timestamp, unit="s"), order.quantity)
          if order.direction == DirectionType.BUY:
            unit_cost = bar.open * (1 + slippage)
          else:
            unit_cost = bar.open * (1 - slippage)
          fill_cost = order.quantity * unit_cost
        else:
          self.order_queue.append(order)  # put it back and wait for next market event
          continue
      fill_event = FillEvent(
        current_time, order.ticker, "", order.quantity, order.direction, fill_cost, unit_cost, slippage
      )
      self.events.put(fill_event)

  def on_order(self, event):
    """
    Processes an OrderEvent to execute trades.
    """
    self.order_queue.append(event)
