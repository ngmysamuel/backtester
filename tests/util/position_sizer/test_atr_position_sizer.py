from unittest.mock import MagicMock

import pytest

from backtester.util.position_sizer.atr_position_sizer import ATRPositionSizer


class FakeDataHandler:
    def __init__(self, bars_map):
        self._bars = bars_map

    def get_latest_bars(self, ticker, n=1):
        return self._bars.get(ticker, [])[-n:]

@pytest.fixture
def mock_data_handler():
    bars = {
        "MSFT": [
            {"high":10, "low":8, "close":9},
            {"high":11, "low":9, "close":10},
            {"high":12, "low":10, "close":11},
            {"high":13, "low":11, "close":12},
            {"high":14, "low":12, "close":13},
            {"high":15, "low":13, "close":14},
        ]
    }
    return FakeDataHandler(bars)

@pytest.fixture
def mock_portfolio(mock_data_handler):
    portfolio = MagicMock()
    portfolio.data_handler = mock_data_handler
    portfolio.current_holdings = {"cash": 100000.0, "total": 100000.0}
    portfolio.risk_per_trade = 0.01
    return portfolio

@pytest.fixture
def atr_position_sizer():
    config = {
        "initial_position_size": 100,
        "atr_window": 5,
        "atr_multiplier": 2
    }
    return ATRPositionSizer(config, ["MSFT"])

def test_calc_atr_insufficient_data(atr_position_sizer, mock_portfolio):
    """Tests that _calc_atr returns None if there is not enough data."""
    mock_portfolio.data_handler._bars["MSFT"] = []
    assert atr_position_sizer._calc_atr(mock_portfolio, "MSFT") is None

def test_calc_atr_correct_calculation(atr_position_sizer, mock_portfolio):
    """Tests that the ATR is calculated correctly based on mock data."""
    atr = atr_position_sizer._calc_atr(mock_portfolio, "MSFT")
    assert atr == pytest.approx(2.0)

def test_get_position_size_updates_with_atr(atr_position_sizer, mock_portfolio):
    """Tests that get_position_size correctly calculates position_size based on ATR."""
    # Simulate that the historical ATR has been calculated on previous bars
    atr_position_sizer.historical_atr["MSFT"] = [2.0]
    
    # capital_to_risk = 0.01 * 100000 = 1000
    # position_size = 1000 // (2.0 * 2) = 250
    position_size = atr_position_sizer.get_position_size(mock_portfolio, "MSFT")
    
    assert position_size == 250

def test_get_position_size_handles_zero_atr(atr_position_sizer, mock_portfolio):
    """Tests that a ZeroDivisionError is avoided if ATR is 0."""
    # Simulate historical ATR of 0
    atr_position_sizer.historical_atr["MSFT"] = [0.0]
    
    position_size = atr_position_sizer.get_position_size(mock_portfolio, "MSFT")
    
    # If ATR is 0, position size should be None
    assert position_size is None
