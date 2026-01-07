from collections import defaultdict
from typing import Any

from backtester.data.data_handler import DataHandler
from backtester.events.market_event import MarketEvent
from backtester.protocols.on_interval_protocol import OnIntervalProtocol
from backtester.util.bar_aggregator import BarAggregator
from backtester.util.util import BarTuple, str_to_seconds


class BarManager:
    def __init__(self, data_handler: DataHandler, news_data_handler: DataHandler, base_interval: str):
        self.data_handler = data_handler
        self.news_data_handler = news_data_handler
        self.base_interval = base_interval

        self.aggregators: dict[tuple[str, str], BarAggregator] = {}  # (ticker, interval) -> aggregator
        self.subscribers: dict[tuple[str, str], list[Any]] = defaultdict(list)  # (ticker, interval) -> list[Any] => the object must implement on_interval

        # TODO: to prune / use deque (reallocation of mem as it grows)
        self.history: dict[tuple[str, str], list[BarTuple]] = defaultdict(list)  # (ticker, interval) -> list[BarTuple]

    def on_heartbeat(self, event: MarketEvent) -> None:
        """
        Handles the base interval - calls the on_hearbeat method on each aggregator registered
        If the on_hearbeat returns an aggregated bar, keep it in self.history and notifies
        any subscribers on the updated history
        Note that such notifications are collated first before notifying the subscribers. This enables
        pairwise trading strategies
        args:
            event - MarketEvent signifying a new heartbeat
        """
        rtn_slice: dict[Any, dict[tuple[str,str], list[BarTuple]]] = defaultdict(dict)  # {subscriber1: {(ticker, interval): [history list]}}
        for key, agg in self.aggregators.items():
            bar = agg.on_heartbeat(event)
            if bar:
                bar["sentiment"] = self.news_data_handler.get_latest_bars(key[0])[-1]
                bar = BarTuple(**bar)
                self.history[key].append(bar)
                for subscriber in self.subscribers[key]:
                    rtn_slice[subscriber][key] = self.history[key]

        # subscriber = subscriber1
        # history = {(ticker,interval): [history list]}
        for subscriber, history in rtn_slice.items():
            subscriber.on_interval(history)

    def subscribe(self, interval: str, ticker: str, subscriber: OnIntervalProtocol) -> None:
        """
        Registers an instance with the BarManager.
        What is this instance? It can be any class as long as it implements an on_interval method.
        This will set up a BarAggregator for every combination of (interval, ticker)
        args:
            interval - the interval the subscriber needs data in
            ticker - the ticker the subscriber needs
            subscriber - satifies the OnIntervalProtocol
        """
        if (ticker, interval) not in self.aggregators:
            self.aggregators[(ticker, interval)] = BarAggregator(str_to_seconds(self.base_interval), str_to_seconds(interval), ticker, self.data_handler)
        self.subscribers[(ticker, interval)].append(subscriber)
