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

    # tmp while position sizing is not implemented
    self.current_positions = {sym: 0 for sym in self.symbol_list}  # to track position history

  def generate_signals(self, event):
    if event.type != "MARKET":
        return
    timestamp = event.timestamp
    for ticker in self.symbol_list:
      data = self.data_handler.get_latest_bars(ticker, n=self.long_window+1)
      if len(data) < self.long_window+1:
        return  # Not enough data to compute moving averages
      short_avg = long_avg = 0
      data = data[:-1] # do not use future data
      for idx, bar in enumerate(data[::-1]):
        if idx < self.short_window:
          short_avg += bar.close
        long_avg += bar.close
      short_avg /= self.short_window
      long_avg /= self.long_window
      if short_avg < long_avg and self.current_positions[ticker] >= 0: # GO SHORT
        self.events.append(SignalEvent(timestamp, ticker, SignalType.SHORT))
        self.current_positions[ticker] = -1
      elif short_avg > long_avg and self.current_positions[ticker] <= 0: # GO LONG
        self.events.append(SignalEvent(timestamp, ticker, SignalType.LONG))
        self.current_positions[ticker] = 1
