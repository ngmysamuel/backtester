import pytest

from backtester.util.position_sizer.atr_position_sizer import ATRPositionSizer
from backtester.util.util import BarTuple


@pytest.fixture
def config():
    return {
        "atr_window": 14,
        "atr_multiplier": 2.0
    }

@pytest.fixture
def sizer(config):
    symbol_list = ["AAPL", "BTC"]
    return ATRPositionSizer(config, symbol_list)

def _create_bars(prices):
    """Helper to create a list of BarTuples from a list of (high, low, close)"""
    bars = []
    for i, (h, l, c) in enumerate(prices):
        bars.append(BarTuple(high=h, low=l, close=c, Index=i, open=1, volume=1, raw_volume=None))
    return bars

def test_initialization(sizer):
    """Ensure the sizer initializes structures correctly."""
    assert sizer.atr_window == 14
    assert "AAPL" in sizer.historical_atr
    assert sizer.historical_atr["AAPL"] == []

def test_on_interval_insufficient_data(sizer):
    """Test that ATR is not calculated if there is not enough history."""
    # Create 10 bars, but window is 14
    bars = _create_bars([(10, 8, 9)] * 10)
    histories = {("AAPL", "1d"): bars}

    sizer.on_interval(histories)

    # Should remain empty because len(bars) < atr_window + 1
    assert len(sizer.historical_atr["AAPL"]) == 0

def test_initial_calculation_arithmetic_mean(sizer):
    """
    The first ATR calculation should be the Arithmetic Mean of the True Ranges 
    over the window.
    """
    # Config: window=2 for simplicity
    simple_config = {"atr_window": 2, "atr_multiplier": 1}
    simple_sizer = ATRPositionSizer(simple_config, ["TEST"])

    # We need window + 1 bars (3 bars) to calculate TR for 2 periods
    # Bar 0: Close = 10
    # Bar 1: H=12, L=10, C=11 (Prev C=10). TR = max(12-10, |12-10|, |10-10|) = 2
    # Bar 2: H=13, L=11, C=12 (Prev C=11). TR = max(13-11, |13-11|, |11-11|) = 2
    bars = _create_bars([
        (11, 9, 10), 
        (12, 10, 11), 
        (13, 11, 12)
    ])
    
    histories = {("TEST", "1d"): bars}
    simple_sizer.on_interval(histories)

    assert len(simple_sizer.historical_atr["TEST"]) == 1
    # Mean of TRs [2, 2] is 2.0
    assert simple_sizer.historical_atr["TEST"][-1] == pytest.approx(2.0)

def test_subsequent_calculation_wilders(sizer):
    """
    Subsequent ATR calculations should use Wilder's Smoothing:
    ATR = (1/n) * TR + (1 - 1/n) * PrevATR
    """
    # Window = 2
    simple_config = {"atr_window": 2, "atr_multiplier": 1}
    simple_sizer = ATRPositionSizer(simple_config, ["TEST"])
    
    # Seed with a previous ATR
    simple_sizer.historical_atr["TEST"] = [2.0]

    # Previous Bar (Index -2 in history)
    prev_bar = BarTuple(high=10, low=10, close=10, Index=0, open=1, volume=1, raw_volume=None)
    # Current Bar (Index -1 in history). 
    # H=14, L=10, PrevC=10. TR = max(4, 4, 0) = 4.
    curr_bar = BarTuple(high=14, low=10, close=12, Index=1, open=1, volume=1, raw_volume=None)

    histories = {("TEST", "1d"): [prev_bar, curr_bar]}
    
    simple_sizer.on_interval(histories)

    # Logic: 1/2 * 4 + (1 - 1/2) * 2.0 = 2 + 1 = 3.0
    assert simple_sizer.historical_atr["TEST"][-1] == pytest.approx(3.0)

def test_get_position_size_integer_rounding(sizer):
    """Test standard integer rounding (e.g. for Stocks)."""
    # Inject known ATR
    sizer.historical_atr["AAPL"] = [2.0]
    
    risk_per_trade = 0.01
    total_equity = 100_000
    rounding = 0
    ticker = "AAPL"
    
    # Logic:
    # Capital to risk = 100,000 * 0.01 = 1,000
    # Multiplier = 2.0 (from config)
    # Stop distance = ATR(2.0) * Multiplier(2.0) = 4.0
    # Position Size = 1,000 / 4.0 = 250
    
    size = sizer.get_position_size(risk_per_trade, total_equity, rounding, ticker)
    assert size == 250
    assert isinstance(size, int)

def test_get_position_size_decimal_rounding(sizer):
    """Test decimal rounding (e.g. for Crypto/Forex)."""
    sizer.historical_atr["BTC"] = [100.0]
    sizer.atr_multiplier = 1.0 # Simplify
    
    risk_per_trade = 0.01
    total_equity = 5555
    rounding = 2 # 2 decimal places
    ticker = "BTC"
    
    # Logic:
    # Capital to risk = 55.55
    # Stop distance = 100 * 1 = 100
    # Raw Size = 0.5555
    # Rounding 2 decimal places (floor) -> 0.55
    
    size = sizer.get_position_size(risk_per_trade, total_equity, rounding, ticker)
    assert size == pytest.approx(0.55)

def test_get_position_size_no_atr_data(sizer):
    """Should return None if ATR has not been calculated yet."""
    # historical_atr is empty by default
    size = sizer.get_position_size(0.01, 10000, 0, "AAPL")
    assert size is None

def test_get_position_size_zero_atr_guard(sizer):
    """Should return None if ATR is 0 to prevent ZeroDivisionError."""
    sizer.historical_atr["AAPL"] = [0.0]
    size = sizer.get_position_size(0.01, 10000, 0, "AAPL")
    assert size is None

def test_get_position_size_reuse_previous(sizer):
    """Sizer returns (None) if there is no history"""
    sizer.historical_atr["AAPL"] = [0.0]
    assert sizer.get_position_size(0.01, 10000, 0, "AAPL") is None