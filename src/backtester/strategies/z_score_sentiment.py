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
        self.historical_sentiment_scores: dict[str, list[float]] = defaultdict(list) # dictionary of ticker to their history of sentiment scores

    def generate_signals(self, histories: dict[str, list[BarTuple]]):
        """
        If the current sentiment is more than threshold standard deviations away from the mean, buy
        """
        for ticker in self.symbol_list:
            latest_bar = histories[(ticker, self.interval)][-1]
            timestamp = latest_bar.Index.timestamp()
            sentiment_score = latest_bar.sentiment.score
            self.historical_sentiment_scores[ticker].append(sentiment_score)
            sentiment_scores = self.historical_sentiment_scores[ticker]
            mean = np.mean(sentiment_scores)
            std = np.std(sentiment_scores)
            if std != 0:
                z_score = (sentiment_score - mean) / std
                if z_score > self.buy_threshold:
                    print(f"strategy is placing a BUY signal: z_score ({z_score}) is higher than threshold ({self.buy_threshold})")
                    self.events.put(SignalEvent(timestamp, ticker, self.name, SignalType.LONG))
                elif z_score < self.sell_threshold:
                    print(f"strategy is placing a SELL signal: z_score ({z_score}) is lower than threshold ({self.sell_threshold})")
                    self.events.put(SignalEvent(timestamp, ticker, self.name, SignalType.SHORT))