import pandas as pd
import pytest
import numpy as np
from backtester.metrics.dashboard import _util as utils

# --- Fixtures for Mock Data ---

@pytest.fixture
def mock_equity_curve_simple():
    """A simple, monotonically increasing equity curve for basic tests."""
    data = {
        "timestamp": pd.to_datetime(["2023-01-01", "2023-01-02", "2023-01-03", "2023-01-04"]),
        "total": [100000, 101000, 102000, 103000],
        "equity_curve": [1.0, 1.01, 1.0199, 1.0297]
    }
    df = pd.DataFrame(data)
    df["returns"] = df["equity_curve"].pct_change()
    df = df.set_index("timestamp")
    return df

@pytest.fixture
def mock_equity_curve_with_drawdown():
    """An equity curve with a clear peak, trough, and recovery period."""
    data = {
        "timestamp": pd.to_datetime([
            "2023-01-01", "2023-01-02", "2023-01-03",  # Peak
            "2023-01-04", "2023-01-05",              # Trough
            "2023-01-06", "2023-01-07"               # Recovery
        ]),
        "total": [100, 110, 120, 105, 100, 115, 125],
        "equity_curve": [1.0, 1.1, 1.2, 1.05, 1.0, 1.15, 1.25]
    }
    df = pd.DataFrame(data)
    df["returns"] = df["equity_curve"].pct_change()
    df = df.set_index("timestamp")
    return df

# --- Test Cases ---

def test_get_total_return(mock_equity_curve_simple):
    """Tests the total return calculation."""
    # Expected: (1.0297 - 1) * 100 = 2.97%
    assert utils.get_total_return(mock_equity_curve_simple) == pytest.approx(2.97, abs=1e-4)

def test_get_sharpe(mock_equity_curve_simple):
    """Tests the Sharpe ratio calculation."""
    returns = mock_equity_curve_simple["returns"].dropna()
    # The new util function calculates the annualization factor dynamically
    annualization_factor = utils.get_annualization_factor(mock_equity_curve_simple)
    expected_sharpe = np.sqrt(annualization_factor) * np.mean(returns) / np.std(returns, ddof=1)
    assert utils.get_sharpe(mock_equity_curve_simple) == pytest.approx(expected_sharpe)

def test_get_cagr(mock_equity_curve_simple):
    """Tests the Compound Annual Growth Rate calculation."""
    pv = mock_equity_curve_simple.iloc[0]["total"]
    fv = mock_equity_curve_simple.iloc[-1]["total"]
    years = (mock_equity_curve_simple.index[-1] - mock_equity_curve_simple.index[0]).days / 365
    expected_cagr = ((fv / pv) ** (1 / years) - 1) * 100
    assert utils.get_cagr(mock_equity_curve_simple) == pytest.approx(expected_cagr)

def test_get_max_drawdown(mock_equity_curve_with_drawdown):
    """Tests the max drawdown calculation, including the duration of the drawdown."""
    max_dd, dd_date, dd_streak, start_date, end_date = utils.get_max_drawdown(mock_equity_curve_with_drawdown)

    # HWM: [1.0, 1.1, 1.2, 1.2, 1.2, 1.2, 1.25]
    # Equity: [1.0, 1.1, 1.2, 1.05, 1.0, 1.15, 1.25]
    # Drawdown %: [0, 0, 0, 12.5, 16.67, 4.17, 0]
    # Max drawdown is 16.67% on 2023-01-05
    assert max_dd == pytest.approx(16.66666, abs=1e-4)
    assert dd_date == "05 Jan, 2023"
    
    # The drawdown starts after the peak (2023-01-03) and lasts for 3 days until it starts recovering.
    # The code finds the longest period the equity curve is below the high-water mark.
    assert dd_streak == 3
    assert start_date == "03 Jan, 2023"
    assert end_date == "06 Jan, 2023"

def test_get_calmar(mock_equity_curve_with_drawdown):
    """Tests the Calmar ratio calculation."""
    cagr = utils.get_cagr(mock_equity_curve_with_drawdown)
    max_dd, _, _, _, _ = utils.get_max_drawdown(mock_equity_curve_with_drawdown)
    expected_calmar = cagr / max_dd
    assert utils.get_calmar(mock_equity_curve_with_drawdown) == pytest.approx(expected_calmar)

def test_get_equity_curve(mock_equity_curve_simple):
    """Tests that the function returns the correct equity curve series."""
    assert isinstance(utils.get_equity_curve(mock_equity_curve_simple), pd.Series)
    assert utils.get_equity_curve(mock_equity_curve_simple).name == "equity_curve"
    assert len(utils.get_equity_curve(mock_equity_curve_simple)) == 4