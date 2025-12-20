from typing import Protocol
from backtester.util.util import BarTuple


class OnIntervalProtocol(Protocol):
    def on_interval(self, history: dict[str, list[BarTuple]]) -> None:
        raise NotImplementedError