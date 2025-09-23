from backtester.events.signal_event import SignalEvent
from backtester.enums.signal_type import SignalType

class MovingAverageCrossover:
  def __init__(self, events, data_handler, short_window=40, long_window=100):
    print(f"Initializing MovingAverageCrossover with short_window={short_window}, long_window={long_window}")
    self.events= events
    self.data_handler = data_handler
    self.symbol_list = data_handler.symbol_list
    self.short_window = short_window
    self.long_window = long_window

  def generate_signals(self, event):
    timestamp = event.timestamp
    ticker = event.ticker
    if event.type != "MARKET" or ticker not in self.symbol_list:
      raise ValueError("Invalid event type or ticker symbol")
    data = self.data_handler.get_latest_bars(ticker, n=self.long_window)
    if len(data) < self.long_window:
      return  # Not enough data to compute moving averages
    short_avg = long_avg = 0
    for idx, bar in enumerate(data[::-1]):
      if idx < self.short_window:
        short_avg += bar.close
      long_avg += bar.close
    short_avg /= self.short_window
    long_avg /= self.long_window
    if short_avg < long_avg: # GO SHORT
      self.events.append(SignalEvent(timestamp, ticker, SignalType.SHORT))
    else: # GO LONG
      self.events.append(SignalEvent(timestamp, ticker, SignalType.LONG))
