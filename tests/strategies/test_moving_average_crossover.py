from collections import deque
from types import SimpleNamespace
import pytest

from backtester.strategies.moving_average_crossover import MovingAverageCrossover
from backtester.events.signal_event import SignalEvent
from backtester.enums.signal_type import SignalType


class FakeDataHandler:
    def __init__(self, symbols, bars_map):
        self.symbol_list = symbols
        self._bars = bars_map

    def get_latest_bars(self, ticker, n=1):
        bars = self._bars.get(ticker, [])
        return bars if n >= len(bars) else bars[-n:]


class FakeEvent:
    def __init__(self, type, ticker):
        self.type = type
        self.ticker = ticker


def make_bars(values):
    return [SimpleNamespace(close=v) for v in values]


def test_not_market_event_raises():
    events = deque()
    dh = FakeDataHandler(["AAPL"], {"AAPL": make_bars([100] * 100)})
    s = MovingAverageCrossover(events, dh)
    ev = FakeEvent("SIGNAL", "AAPL")
    with pytest.raises(ValueError):
        s.generate_signals(ev)


def test_unknown_ticker_raises():
    events = deque()
    dh = FakeDataHandler(["AAPL"], {"AAPL": make_bars([100] * 100)})
    s = MovingAverageCrossover(events, dh)
    ev = FakeEvent("MARKET", "MSFT")
    with pytest.raises(ValueError):
        s.generate_signals(ev)


def test_insufficient_bars_no_signal():
    events = deque()
    dh = FakeDataHandler(["AAPL"], {"AAPL": make_bars([100] * 50)})
    s = MovingAverageCrossover(events, dh, short_window=10, long_window=100)
    ev = FakeEvent("MARKET", "AAPL")
    s.generate_signals(ev)
    assert len(events) == 0
    assert s.current_positions["AAPL"] == 0


def test_no_signal_when_ma_equal():
    events = deque()
    bars = make_bars([100] * 100)
    dh = FakeDataHandler(["AAPL"], {"AAPL": bars})
    s = MovingAverageCrossover(events, dh, short_window=40, long_window=100)
    ev = FakeEvent("MARKET", "AAPL")
    s.generate_signals(ev)
    assert len(events) == 0
    assert s.current_positions["AAPL"] == 0


def test_long_signal_when_short_crosses_above():
    events = deque()
    # 60 bars at 100, 40 bars at 200 -> short_avg > long_avg
    bars = make_bars([100] * 60 + [200] * 40)
    dh = FakeDataHandler(["AAPL"], {"AAPL": bars})
    s = MovingAverageCrossover(events, dh, short_window=40, long_window=100)
    ev = FakeEvent("MARKET", "AAPL")
    s.generate_signals(ev)
    assert len(events) == 1
    sig = events.pop()
    assert isinstance(sig, SignalEvent)
    assert sig.symbol == "AAPL"
    assert sig.signal_type == SignalType.LONG
    assert s.current_positions["AAPL"] == 1


def test_short_signal_when_short_crosses_below():
    events = deque()
    # 60 bars at 200, 40 bars at 100 -> short_avg < long_avg
    bars = make_bars([200] * 60 + [100] * 40)
    dh = FakeDataHandler(["AAPL"], {"AAPL": bars})
    s = MovingAverageCrossover(events, dh, short_window=40, long_window=100)
    ev = FakeEvent("MARKET", "AAPL")
    s.generate_signals(ev)
    assert len(events) == 1
    sig = events.pop()
    assert sig.signal_type == SignalType.SHORT
    assert s.current_positions["AAPL"] == -1


def test_no_duplicate_signals_on_repeated_events():
    events = deque()
    bars = make_bars([100] * 60 + [200] * 40)
    dh = FakeDataHandler(["AAPL"], {"AAPL": bars})
    s = MovingAverageCrossover(events, dh, short_window=40, long_window=100)
    ev = FakeEvent("MARKET", "AAPL")
    s.generate_signals(ev)
    assert len(events) == 1
    # second call should not append because current_positions is already 1
    s.generate_signals(ev)
    assert len(events) == 1


def test_positions_are_per_symbol():
    events = deque()
    bars_a = make_bars([100] * 60 + [200] * 40)
    bars_b = make_bars([200] * 60 + [100] * 40)
    dh = FakeDataHandler(["AAPL", "MSFT"], {"AAPL": bars_a, "MSFT": bars_b})
    s = MovingAverageCrossover(events, dh, short_window=40, long_window=100)
    s.generate_signals(FakeEvent("MARKET", "AAPL"))
    s.generate_signals(FakeEvent("MARKET", "MSFT"))
    assert len(events) == 2
    assert s.current_positions["AAPL"] == 1
    assert s.current_positions["MSFT"] == -1

@pytest.mark.parametrize(
    "short_window,long_window,values,expected",
    [
        # short < long and last values high -> LONG
        (3, 5, [1,1,1,10,10], SignalType.LONG),
        # short < long and last values low -> SHORT
        (3, 5, [10,10,10,1,1], SignalType.SHORT),
        # equal averages -> None (no signal)
        (2, 4, [5,5,5,5], None),
    ],
)
def test_parameterized_ma_cases(short_window, long_window, values, expected):
    events = deque()
    bars = make_bars(values)
    dh = FakeDataHandler(["AAPL"], {"AAPL": bars})
    s = MovingAverageCrossover(events, dh, short_window=short_window, long_window=long_window)
    ev = FakeEvent("MARKET", "AAPL")
    s.generate_signals(ev)
    if expected is None:
        assert len(events) == 0
    else:
        assert len(events) == 1
        sig = events.pop()
        assert sig.signal_type == expected


def test_sequence_evolving_data_detects_crossover():
    # Start with a condition that produces SHORT, then extend with newer highs to flip to LONG
    events = deque()
    # last 20: 10 highs (200) followed by 10 lows (100) -> short_avg (last10)=100 < long_avg=150
    seq_values = [200] * 10 + [100] * 10
    seq = make_bars(seq_values)
    dh = FakeDataHandler(["AAPL"], {"AAPL": seq})
    s = MovingAverageCrossover(events, dh, short_window=10, long_window=20)
    ev = FakeEvent("MARKET", "AAPL")
    # First call should produce SHORT
    s.generate_signals(ev)
    assert len(events) == 1
    first = events.pop()
    assert first.signal_type == SignalType.SHORT

    # Now simulate new bars arriving that flip the averages to LONG by adding recent highs
    new_bars = make_bars(seq_values + [200] * 10)
    dh2 = FakeDataHandler(["AAPL"], {"AAPL": new_bars})
    s2 = MovingAverageCrossover(events, dh2, short_window=10, long_window=20)
    ev2 = FakeEvent("MARKET", "AAPL")
    s2.generate_signals(ev2)
    assert len(events) == 1
    second = events.pop()
    assert second.signal_type == SignalType.LONG
