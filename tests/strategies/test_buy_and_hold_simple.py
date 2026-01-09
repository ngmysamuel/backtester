import queue
from datetime import datetime

from backtester.strategies.buy_and_hold_simple import BuyAndHoldSimple
from backtester.events.signal_event import SignalEvent
from backtester.enums.signal_type import SignalType
from backtester.util.util import BarTuple, SentimentTuple


def create_sample_bar(index: datetime, close: float = 100.0) -> BarTuple:
    """Helper function to create a sample BarTuple for testing."""
    return BarTuple(
        Index=index,
        open=close - 1,
        high=close + 1,
        low=close - 1,
        close=close,
        volume=1000,
        raw_volume=1000,
        sentiment=SentimentTuple(Index=index, score=0.0)
    )


def test_initialization_sets_bought_flags():
    events = queue.Queue()
    symbol_list = ["AAPL", "MSFT"]
    s = BuyAndHoldSimple(events, "test_strategy", symbol_list=symbol_list, interval=86400)
    assert s.bought == {"AAPL": False, "MSFT": False}
    assert s.days_before_buying == 21  # default value


def test_initialization_with_custom_days_before_buying():
    events = queue.Queue()
    symbol_list = ["AAPL"]
    s = BuyAndHoldSimple(events, "test_strategy", symbol_list=symbol_list, interval=86400, days_before_buying=5)
    assert s.days_before_buying == 5


def test_generate_signals_before_days_before_buying_no_signal():
    events = queue.Queue()
    symbol_list = ["AAPL"]
    s = BuyAndHoldSimple(events, "test_strategy", symbol_list=symbol_list, interval=86400, days_before_buying=3)

    # Call generate_signals twice (less than days_before_buying)
    timestamp = datetime(2023, 1, 1)
    history = {("AAPL", "1d"): [create_sample_bar(timestamp)]}

    s.generate_signals(history)
    s.generate_signals(history)

    # No signals should be generated yet
    assert events.empty()
    assert s.bought["AAPL"] is False
    assert s.counter == 2


def test_generate_signals_happy_path_appends_signal_once():
    events = queue.Queue()
    symbol_list = ["AAPL"]
    s = BuyAndHoldSimple(events, "test_strategy", symbol_list=symbol_list, interval=86400, days_before_buying=1)

    timestamp = datetime(2023, 1, 1)
    history = {("AAPL", "1d"): [create_sample_bar(timestamp)]}

    # First call should generate signal
    s.generate_signals(history)
    events_list = list(events.queue)
    assert len(events_list) == 1
    sig = events_list[0]
    assert isinstance(sig, SignalEvent)
    assert sig.ticker == "AAPL"
    assert sig.signal_type == SignalType.LONG
    assert s.bought["AAPL"] is True

    # Second call should not append another signal
    s.generate_signals(history)
    events_list = list(events.queue)
    assert len(events_list) == 1


def test_generate_signals_empty_history_no_signal():
    events = queue.Queue()
    symbol_list = ["AAPL"]
    s = BuyAndHoldSimple(events, "test_strategy", symbol_list=symbol_list, interval=86400, days_before_buying=1)

    # Empty history
    history = {("AAPL", "1d"): []}

    s.generate_signals(history)
    # No signal should be appended when there is no market data
    assert events.empty()
    assert s.bought["AAPL"] is False


def test_multiple_symbols_all_bought_independently():
    events = queue.Queue()
    symbol_list = ["AAPL", "MSFT"]
    s = BuyAndHoldSimple(events, "test_strategy", symbol_list=symbol_list, interval=86400, days_before_buying=1)

    timestamp = datetime(2023, 1, 1)
    history = {
        ("AAPL", "1d"): [create_sample_bar(timestamp, 100.0)],
        ("MSFT", "1d"): [create_sample_bar(timestamp, 200.0)]
    }

    s.generate_signals(history)
    events_list = list(events.queue)
    assert len(events_list) == 2

    # Check both signals
    tickers = {sig.ticker for sig in events_list}
    assert tickers == {"AAPL", "MSFT"}

    # bought flags set
    assert s.bought["AAPL"] and s.bought["MSFT"]


def test_generate_signals_continues_if_one_symbol_has_no_data():
    events = queue.Queue()
    symbol_list = ["AAPL", "MSFT"]
    s = BuyAndHoldSimple(events, "test_strategy", symbol_list=symbol_list, interval=86400, days_before_buying=1)

    timestamp = datetime(2023, 1, 1)
    # MSFT has no data
    history = {
        ("AAPL", "1d"): [create_sample_bar(timestamp, 100.0)],
        ("MSFT", "1d"): []
    }

    s.generate_signals(history)

    # Should still generate a signal for AAPL
    events_list = list(events.queue)
    assert len(events_list) == 1
    sig = events_list[0]
    assert sig.ticker == "AAPL"
    assert s.bought["AAPL"] is True

    # MSFT should not be bought
    assert s.bought["MSFT"] is False
