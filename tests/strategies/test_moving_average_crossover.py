import pytest
from queue import Queue
from types import SimpleNamespace

from backtester.strategies.moving_average_crossover import MovingAverageCrossover
from backtester.events.signal_event import SignalEvent
from backtester.enums.signal_type import SignalType

# --- Test Helpers ---

class FakeDataHandler:
    """A fake data handler that can be updated with new bars."""
    def __init__(self, symbols, initial_bars_map=None):
        self.symbol_list = symbols
        self._bars = initial_bars_map if initial_bars_map else {}

    def get_latest_bars(self, ticker, n=1):
        """Returns the latest N bars for a given ticker."""
        bars = self._bars.get(ticker, [])
        return bars if n >= len(bars) else bars[-n:]

    def update_bars(self, ticker, new_bars):
        """Appends new bars for a ticker."""
        if ticker not in self._bars:
            self._bars[ticker] = []
        self._bars[ticker].extend(new_bars)

def make_bars(values):
    """Factory function to create a list of bar objects with a 'close' attribute."""
    return [SimpleNamespace(close=v) for v in values]

# --- Tests ---

def test_not_market_event_no_signal():
    """Strategy should not generate signals for non-MARKET events."""
    events = Queue()
    dh = FakeDataHandler(["AAPL"])
    s = MovingAverageCrossover(events, dh)
    # A non-market event
    event = SimpleNamespace(type="ORDER", timestamp=123)
    s.generate_signals(event)
    assert events.qsize() == 0

def test_insufficient_bars_no_signal():
    """Strategy should not generate a signal if there are not enough bars."""
    events = Queue()
    # Not enough bars for the long window
    bars = make_bars([100] * 50)
    dh = FakeDataHandler(["AAPL"], {"AAPL": bars})
    s = MovingAverageCrossover(events, dh, short_window=10, long_window=100)
    event = SimpleNamespace(type="MARKET", timestamp=123)
    s.generate_signals(event)
    assert events.qsize() == 0
    assert s.current_positions["AAPL"] == 0

def test_no_signal_when_ma_equal():
    """Strategy should not generate a signal when moving averages are equal."""
    events = Queue()
    bars = make_bars([100] * 101) # 101 bars to satisfy long_window+1
    dh = FakeDataHandler(["AAPL"], {"AAPL": bars})
    s = MovingAverageCrossover(events, dh, short_window=40, long_window=100)
    event = SimpleNamespace(type="MARKET", timestamp=123)
    s.generate_signals(event)
    assert events.qsize() == 0
    assert s.current_positions["AAPL"] == 0

def test_long_signal_when_short_crosses_above():
    """Strategy should generate a LONG signal when the short MA crosses above the long MA."""
    events = Queue()
    # 61 bars at 100, 40 bars at 200 -> short_avg > long_avg
    bars = make_bars([100] * 61 + [200] * 40)
    dh = FakeDataHandler(["AAPL"], {"AAPL": bars})
    s = MovingAverageCrossover(events, dh, short_window=40, long_window=100)
    event = SimpleNamespace(type="MARKET", timestamp=123)
    s.generate_signals(event)
    assert events.qsize() == 1
    sig = events.get()
    assert isinstance(sig, SignalEvent)
    assert sig.ticker == "AAPL"
    assert sig.signal_type == SignalType.LONG
    assert s.current_positions["AAPL"] == 1

def test_short_signal_when_short_crosses_below():
    """Strategy should generate a SHORT signal when the short MA crosses below the long MA."""
    events = Queue()
    # 61 bars at 200, 40 bars at 100 -> short_avg < long_avg
    bars = make_bars([200] * 61 + [100] * 40)
    dh = FakeDataHandler(["AAPL"], {"AAPL": bars})
    s = MovingAverageCrossover(events, dh, short_window=40, long_window=100)
    event = SimpleNamespace(type="MARKET", timestamp=123)
    s.generate_signals(event)
    assert events.qsize() == 1
    sig = events.get()
    assert sig.signal_type == SignalType.SHORT
    assert s.current_positions["AAPL"] == -1

def test_no_duplicate_signals_on_repeated_events():
    """Strategy should not generate a new signal if the position is already established."""
    events = Queue()
    bars = make_bars([100] * 61 + [200] * 40)
    dh = FakeDataHandler(["AAPL"], {"AAPL": bars})
    s = MovingAverageCrossover(events, dh, short_window=40, long_window=100)
    event = SimpleNamespace(type="MARKET", timestamp=123)
    # First call generates a LONG signal
    s.generate_signals(event)
    assert events.qsize() == 1
    # Second call should not generate another signal because position is already 1
    s.generate_signals(event)
    assert events.qsize() == 1

def test_processes_all_symbols_on_market_event():
    """Strategy should process all symbols in its list on a market event."""
    events = Queue()
    # AAPL should generate LONG, MSFT should generate SHORT
    bars_aapl = make_bars([100] * 61 + [200] * 40)
    bars_msft = make_bars([200] * 61 + [100] * 40)
    dh = FakeDataHandler(["AAPL", "MSFT"], {"AAPL": bars_aapl, "MSFT": bars_msft})
    s = MovingAverageCrossover(events, dh, short_window=40, long_window=100)
    event = SimpleNamespace(type="MARKET", timestamp=123)
    s.generate_signals(event)
    assert events.qsize() == 2
    assert s.current_positions["AAPL"] == 1
    assert s.current_positions["MSFT"] == -1
    # Check signals
    signals = {e.ticker: e.signal_type for e in list(events.queue)}
    assert signals["AAPL"] == SignalType.LONG
    assert signals["MSFT"] == SignalType.SHORT

@pytest.mark.parametrize(
    "short_window,long_window,values,expected_signal",
    [
        # short > long -> LONG
        (3, 5, [1, 1, 1, 10, 10, 10], SignalType.LONG),
        # short < long -> SHORT
        (3, 5, [10, 10, 10, 1, 1, 1], SignalType.SHORT),
        # equal averages -> None (no signal)
        (2, 4, [5, 5, 5, 5, 5], None),
    ],
)
def test_parameterized_ma_cases(short_window, long_window, values, expected_signal):
    """Tests various moving average scenarios with parameterized inputs."""
    events = Queue()
    bars = make_bars(values)
    dh = FakeDataHandler(["AAPL"], {"AAPL": bars})
    s = MovingAverageCrossover(events, dh, short_window=short_window, long_window=long_window)
    event = SimpleNamespace(type="MARKET", timestamp=123)
    s.generate_signals(event)
    if expected_signal is None:
        assert events.qsize() == 0
    else:
        assert events.qsize() == 1
        sig = events.get()
        assert sig.signal_type == expected_signal

def test_sequence_evolving_data_detects_crossover():
    """
    Tests that a single strategy instance correctly detects a crossover
    as new data arrives over time.
    """
    events = Queue()
    dh = FakeDataHandler(["AAPL"])
    s = MovingAverageCrossover(events, dh, short_window=10, long_window=20)
    event = SimpleNamespace(type="MARKET", timestamp=123)

    # --- Step 1: Initial state, should produce SHORT ---
    # last 20 bars: 11 highs (200) followed by 10 lows (100)
    # short_avg (last 10) = 100; long_avg (last 20) = (11*200 + 10*100)/20 = 160 -> SHORT
    initial_bars = make_bars([200] * 11 + [100] * 10)
    dh.update_bars("AAPL", initial_bars)
    s.generate_signals(event)

    assert events.qsize() == 1
    first_signal = events.get()
    assert first_signal.signal_type == SignalType.SHORT
    assert s.current_positions["AAPL"] == -1

    # --- Step 2: New data arrives, should flip to LONG ---
    # Add 10 new bars at 200. The latest 20 bars are now 10 at 100, 10 at 200.
    # The latest 21 bars are [200]*1 + [100]*10 + [200]*10
    # The data used for calculation is [200]*1 + [100]*10 + [200]*9
    # short_avg (last 10) = (1*100 + 9*200)/10 = 190
    # long_avg (last 20) = (1*200 + 10*100 + 9*200)/20 = 150 -> LONG
    new_bars = make_bars([200] * 10)
    dh.update_bars("AAPL", new_bars)
    s.generate_signals(event)

    assert events.qsize() == 1
    second_signal = events.get()
    assert second_signal.signal_type == SignalType.LONG
    assert s.current_positions["AAPL"] == 1
