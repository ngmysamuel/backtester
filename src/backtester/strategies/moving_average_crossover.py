from backtester.strategies.strategy import Strategy
from backtester.enums.signal_type import SignalType
from backtester.events.signal_event import SignalEvent
import queue
from backtester.util.util import BarTuple

class MovingAverageCrossover(Strategy):
    def __init__(self, events: queue.Queue, name: str, **kwargs):
        super().__init__(events, name, kwargs["symbol_list"], kwargs["interval"])
        self.short_window = kwargs.get("short_window", 40)
        self.long_window = kwargs.get("long_window", 100)
        self.current_positions = {sym: 0 for sym in self.symbol_list}  # to track position history
        print(f"Initializing MovingAverageCrossover with short_window={self.short_window}, long_window={self.long_window}")

    def generate_signals(self, histories: dict[tuple[str,str], list[BarTuple]]):
        for (ticker,interval), history in histories.items(): #TODO: should loop over this strategy's tickers rather than all tickers in histories
            if not history:
                continue
            timestamp = history[-1].Index.timestamp()

            data = history[-self.long_window - 1:]
            if len(data) < self.long_window + 1:
                return  # Not enough data to compute moving averages
            short_avg = long_avg = 0
            data = data[:-1]  # do not use future data
            for idx, bar in enumerate(data[::-1]):
                if idx < self.short_window:
                    short_avg += bar.close
                long_avg += bar.close
            short_avg /= self.short_window
            long_avg /= self.long_window
            if short_avg < long_avg and self.current_positions[ticker] >= 0:  # GO SHORT
                self.events.put(SignalEvent(timestamp, ticker, self.name, SignalType.SHORT))
                self.current_positions[ticker] = -1
            elif short_avg > long_avg and self.current_positions[ticker] <= 0:  # GO LONG
                self.events.put(SignalEvent(timestamp, ticker, self.name, SignalType.LONG))
                self.current_positions[ticker] = 1
