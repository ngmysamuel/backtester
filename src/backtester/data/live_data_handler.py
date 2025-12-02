from backtester.data.data_handler import DataHandler
import threading
import yfinance as yf
from datetime import datetime
from queue import Queue
import time
import pandas as pd
from backtester.events.market_event import MarketEvent
from collections import namedtuple
from backtester.util.util import str_to_seconds


class LiveDataHandler(DataHandler):
  """
  Spin up 2 threads
    1. listens on the websocket
        push any received messages into a thread safe queue
    2. sets the current time as start time,
        sleeps for <interval> period of time,
        on waking up, consumes the queue till there are no more events or the message's timestamp is more than start time + interval
        sets the O H L C of the bar and calls update_bars()
  Need to update the main event loop
    1. NOT call update_bars() if we are using live data
    2. only call portfolio.end_of_interval() if we had gone into the "while event_queue" loop. See below Assumptions (1)
  Assumptions
    1. The "while event_queue" loop does not take longer than <interval> time
      if take longer, we are missing calling portfolio.end_of_interval()
      move portfolio.end_of_interval() to on MARKET event block?
      keep track of the current interval start time in the "while event_queue" loop as well?
  """

  def __init__(self, event_queue: list, symbol_list: list, interval: str, period: str, exchange_closing_time: str):
    self.event_queue = event_queue
    self.interval = str_to_seconds(interval)
    self.period = str_to_seconds(period)
    self.symbol_list = symbol_list
    self.exchange_closing_time = exchange_closing_time

    self.message_queue = Queue()
    self.BarTuple = namedtuple("Bar", ["Index", "open", "high", "low", "close"])
    self.bar_dict = {ticker: {} for ticker in symbol_list}
    self.symbol_raw_data = {ticker: [] for ticker in symbol_list}
    self.latest_symbol_data = {ticker: [] for ticker in symbol_list}
    self.continue_backtest = True

    message_listener = threading.Thread(target=self._start_listening, args=(symbol_list,))
    message_listener.daemon = True
    aggregator = threading.Thread(target=self._start_aggregating)
    aggregator.daemon = True
    self.beginning_time = datetime.now().timestamp()
    self.start_time = self.beginning_time
    self.end_time = self.start_time + self.interval - 1
    self.final_time = self.start_time + self.period
    message_listener.start()
    aggregator.start()

  def _start_aggregating(self):
    """
    Aggregates all messages from the websocket into a single bar
    """
    current_time = self.start_time
    next_time = self.start_time + self.interval # to negate drift
    while current_time < self.final_time:
      sleep_time = next_time - datetime.now().timestamp()
      if sleep_time > 0:
        time.sleep(self.interval)
      next_time += self.interval
      while not self.message_queue.empty():
        message = self.message_queue.get(block=False)
        ticker = message["id"]
        price = message["price"]
        current_time = float(message["time"])
        if current_time > self.end_time:  # we are in a new interval alr, push out whatever is present
          self._finalize_and_push_bars()
        if not self.bar_dict[ticker]:  # we are starting a new interval, reset bar_dict
          self.start_time = self.end_time + 1
          self.end_time = self.start_time + self.interval - 1
          self.bar_dict[ticker] = {"Index": pd.to_datetime(self.start_time, unit="s").tz_localize(None), "open": price, "high": price, "low": price, "close": price}
        else:  # we are still in the same interval, continue updating high, low, and close prices
          bar = self.bar_dict[ticker]
          bar["high"] = max(bar["high"], price)
          bar["low"] = max(bar["low"], price)
          bar["close"] = price

    self.continue_backtest = False
    self.symbol_raw_data = {key: pd.DataFrame(val) for key, val in self.symbol_raw_data.items()}

  def _finalize_and_push_bars(self):
    """
    Pushes the latest bar to the latest_symbol_data structure for all
    symbols in the symbol list. This will also generate a MarketEvent.
    """
    mkt_close = False
    for symbol in self.symbol_list:
      bar = self.bar_dict[symbol]
      if not bar:
        if len(self.latest_symbol_data[symbol]) > 0:  # if we have previous data and only this interval has no movement, use previous data
          bar = self.latest_symbol_data[symbol][-1]
        else:  # if no previous data, then this interval will have no data as well
          bar = None

      if bar is not None:
        bar = self.BarTuple(**bar)
        self.symbol_raw_data[symbol].append(bar)
        self.latest_symbol_data[symbol].append(bar)
        mkt_close = bar.Index + pd.Timedelta(self.interval) >= bar.Index.replace(hour=int(self.exchange_closing_time.split(":")[0]), minute=int(self.exchange_closing_time.split(":")[1]))

      self.bar_dict[symbol] = {}  # reset for the next interval

    self.event_queue.append(MarketEvent(self.start_time, mkt_close))

  def update_bars(self):
    """
    In live trading, the background thread handles bar generation.
    This method is a stub to satisfy the DataHandler interface.
    """
    pass

  def get_latest_bars(self, symbol: str, n: int = 1):
    """
    Returns the last N bars from the latest_symbol_data
    """
    return self.latest_symbol_data[symbol][-n:]

  def _start_listening(self, symbol_list: list):
    with yf.WebSocket() as ws:
      ws.subscribe(symbol_list)
      ws.listen(self._handle_message)

  def _handle_message(self, message):
    """
    {'id': 'AAPL', 'price': 239.8471, 'time': '1758116301000', 'exchange': 'NMS', 'quote_type': 8, 'market_hours': 1, 'change_percent': 0.7126236, 'day_volume': '3618459', 'change': 1.697113, 'price_hint': '2'}
    """
    self.message_queue.put(message)