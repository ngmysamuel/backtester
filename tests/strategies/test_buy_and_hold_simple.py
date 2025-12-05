from queue import Queue

from backtester.strategies.buy_and_hold_simple import BuyAndHoldSimple
from backtester.events.signal_event import SignalEvent
from backtester.enums.signal_type import SignalType


class FakeDataHandler:
    def __init__(self, symbols, latest_bars=None):
        self.symbol_list = symbols
        self._latest_bars = latest_bars or {}

    def get_latest_bars(self, ticker, n=1):
        return self._latest_bars.get(ticker, [])


class FakeEvent:
    def __init__(self, timestamp=1234567890):
        self.type = "MARKET"
        self.timestamp = timestamp
        self.ticker = None


def test_initialization_sets_bought_flags():
    dh = FakeDataHandler(["AAPL", "MSFT"])
    s = BuyAndHoldSimple(Queue(), dh)
    assert s.bought == {"AAPL": False, "MSFT": False}


def test_generate_signals_happy_path_appends_signal_once():
    events = Queue()
    dh = FakeDataHandler(["AAPL"], latest_bars={"AAPL": [{"close": 100}]})
    s = BuyAndHoldSimple(events, dh)
    ev = FakeEvent()
    s.generate_signals(ev)
    events_list = list(events.queue)
    assert len(events_list) == 1
    sig = events_list[0]
    assert isinstance(sig, SignalEvent)
    assert sig.ticker == "AAPL"
    assert sig.signal_type == SignalType.LONG

    # second MARKET should not append another signal
    s.generate_signals(ev)
    events_list = list(events.queue)
    assert len(events_list) == 1


def test_get_latest_bars_empty_no_signal_appended():
    events = Queue()
    dh = FakeDataHandler(["AAPL"], latest_bars={"AAPL": []})
    s = BuyAndHoldSimple(events, dh)
    ev = FakeEvent()
    s.generate_signals(ev)
    # No signal should be appended when there is no market data
    events_list = list(events.queue)
    assert len(events_list) == 0
    assert s.bought["AAPL"] is False


def test_multiple_symbols_all_bought_independently():
    events = Queue()
    dh = FakeDataHandler(["AAPL", "MSFT"], latest_bars={"AAPL": [1], "MSFT": [2]})
    s = BuyAndHoldSimple(events, dh)
    s.generate_signals(FakeEvent())
    events_list = list(events.queue)
    assert len(events_list) == 2
    # bought flags set
    assert s.bought["AAPL"] and s.bought["MSFT"]


def test_generate_signals_continues_if_one_symbol_has_no_data():
    events = Queue()
    # MSFT has no data
    dh = FakeDataHandler(["AAPL", "MSFT"], latest_bars={"AAPL": [{"close": 100}]})
    s = BuyAndHoldSimple(events, dh)
    ev = FakeEvent()
    s.generate_signals(ev)

    # Should still generate a signal for AAPL
    events_list = list(events.queue)
    assert len(events_list) == 1
    sig = events_list[0]
    assert sig.ticker == "AAPL"
    assert s.bought["AAPL"] is True

    # MSFT should not be bought
    assert s.bought["MSFT"] is False