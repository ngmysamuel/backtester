from backtester.strategies.strategy import Strategy
import queue
from backtester.util.util import BarTuple
from backtester.enums.signal_type import SignalType
from backtester.events.signal_event import SignalEvent
from collections import defaultdict
import numpy as np
class ZScoreSentiment(Strategy):
    def __init__(self, events: queue.Queue, name: str, **kwargs):
        super().__init__(events, name, kwargs["symbol_list"], kwargs["interval"])
        self.buy_threshold = kwargs["buy_threshold"]
        self.sell_threshold = kwargs["sell_threshold"]
        self.sentiment_scores: dict[str, list[float]] = defaultdict(list)

    def generate_signals(self, histories: dict[str, list[BarTuple]]):
        """
        If the current sentiment is more than threshold standard deviations away from the mean, buy
        """
        for ticker in self.symbol_list:
            history = histories[ticker]
            timestamp = history.Index.timestamp()
            sentiment_score = history.sentiment.score
            historical_sentiment_score = self.sentiment_scores[ticker]
            historical_sentiment_score.append(sentiment_score)
            mean = np.mean(historical_sentiment_score)
            z_score = (sentiment_score - mean) / np.std(historical_sentiment_score)
            if z_score > self.buy_threshold:
                print(f"strategy is placing a BUY signal: z_score ({z_score}) is higher than threshold ({self.buy_threshold})")
                self.events.put(SignalEvent(timestamp, ticker, self.name, SignalType.LONG))
            elif z_score < self.sell_threshold:
                print(f"strategy is placing a SELL signal: z_score ({z_score}) is lower than threshold ({self.sell_threshold})")
                self.events.put(SignalEvent(timestamp, ticker, self.name, SignalType.SHORT))