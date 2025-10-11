import pandas as pd
import pytest
import numpy as np
from backtester.metrics.dashboard import _util as utils
import plotly
from scipy.stats import norm
from millify import millify

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

@pytest.fixture
def mock_equity_curve_with_trades():
    """An equity curve with a column for trade orders."""
    data = {
        "timestamp": pd.to_datetime(["2023-01-01", "2023-01-02", "2023-01-03", "2023-01-04", "2023-01-05"]),
        "total": [100000, 101000, 102000, 103000, 104000],
        "equity_curve": [1.0, 1.01, 1.02, 1.03, 1.04],
        "order": [
            "BUY 10 AAPL @ 150.0",
            "",
            "SELL 5 AAPL @ 155.0 | BUY 20 MSFT @ 300.0",
            "SELL 10 MSFT @ 305.0",
            ""
        ]
    }
    df = pd.DataFrame(data).set_index("timestamp")
    return df

@pytest.fixture
def mock_trades_df():
    """A mock DataFrame of parsed trades, similar to the output of get_trades."""
    trade_data = {
        "Date": pd.to_datetime(["2023-01-01", "2023-01-02", "2023-01-03", "2023-01-04"]),
        "Direction": ["BUY", "SELL", "SELL", "BUY"],
        "Quantity": [10, 5, 10, 10],
        "Ticker": ["AAPL", "AAPL", "MSFT", "MSFT"],
        "Unit Price": ["$150.0", "$155.0", "$300.0", "$290.0"]
    }
    return pd.DataFrame(trade_data)

@pytest.fixture
def mock_long_equity_curve():
    """A longer, more volatile equity curve for rolling calculations."""
    np.random.seed(42)
    dates = pd.to_datetime(pd.date_range(start="2023-01-01", periods=70, freq="D"))
    # Create some volatility
    returns = np.random.normal(loc=0.001, scale=0.02, size=70)
    equity_curve = (1 + returns).cumprod()
    
    df = pd.DataFrame({
        "timestamp": dates,
        "equity_curve": equity_curve,
        "total": 100000 * equity_curve
    })
    df["returns"] = df["equity_curve"].pct_change()
    df = df.set_index("timestamp")
    return df

# --- Test Cases ---

@pytest.mark.parametrize("interval, expected_factor", [
    ("1m", 252 * 6.5 * 60),
    ("15m", 252 * 6.5 * 4),
    ("1h", 252 * 6.5),
    ("1d", 252),
    ("1mo", 12),
])
def test_get_annualization_factor_valid(interval, expected_factor):
    """Tests that the annualization factor is calculated correctly for valid intervals."""
    assert utils.get_annualization_factor(interval) == pytest.approx(expected_factor)

def test_get_annualization_factor_invalid():
    """Tests that a ValueError is raised for an unsupported interval."""
    with pytest.raises(ValueError):
        utils.get_annualization_factor("unsupported_interval")

def test_get_total_return(mock_equity_curve_simple):
    """Tests the total return calculation."""
    # Expected: (1.0297 - 1) * 100 = 2.97%
    assert utils.get_total_return(mock_equity_curve_simple) == pytest.approx(2.97, abs=1e-4)

def test_get_sharpe(mock_equity_curve_simple):
    """Tests the Sharpe ratio calculation."""
    returns = mock_equity_curve_simple["returns"].dropna()
    annualization_factor = utils.get_annualization_factor("1d")
    expected_sharpe = np.sqrt(annualization_factor) * np.mean(returns) / np.std(returns, ddof=1)
    assert utils.get_sharpe(mock_equity_curve_simple, "1d") == pytest.approx(expected_sharpe)

def test_get_cagr(mock_equity_curve_simple):
    """Tests the Compound Annual Growth Rate calculation."""
    pv = mock_equity_curve_simple.iloc[0]["total"]
    fv = mock_equity_curve_simple.iloc[-1]["total"]
    annualization_factor = utils.get_annualization_factor("1d")
    years = len(mock_equity_curve_simple) / annualization_factor
    expected_cagr = ((fv / pv) ** (1 / years) - 1) * 100
    assert utils.get_cagr(mock_equity_curve_simple, "1d") == pytest.approx(expected_cagr)

def test_get_max_drawdown_no_drawdown(mock_equity_curve_simple):
    """Tests max drawdown calculation when there is no drawdown."""
    max_dd, _, dd_streak, _, _ = utils.get_max_drawdown(mock_equity_curve_simple)
    assert max_dd == 0
    assert dd_streak == 0

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
    cagr = utils.get_cagr(mock_equity_curve_with_drawdown, "1d")
    max_dd, _, _, _, _ = utils.get_max_drawdown(mock_equity_curve_with_drawdown)
    expected_calmar = cagr / max_dd
    assert utils.get_calmar(mock_equity_curve_with_drawdown, "1d") == pytest.approx(expected_calmar)

def test_get_calmar_no_drawdown(mock_equity_curve_simple):
    """Tests the Calmar ratio calculation when max drawdown is zero."""
    assert utils.get_calmar(mock_equity_curve_simple, "1d") == np.inf

def test_get_equity_curve(mock_equity_curve_simple):
    """Tests that the function returns a valid Plotly figure."""
    fig = utils.get_equity_curve(mock_equity_curve_simple)
    
    assert isinstance(fig, plotly.graph_objects.Figure)
    # Check that there is one line trace in the figure
    assert len(fig.data) == 1
    # Check that the data in the trace matches the mock data
    trace = fig.data[0]
    assert list(trace.y) == list(mock_equity_curve_simple["equity_curve"])
    assert list(trace.x) == list(mock_equity_curve_simple.index)

def test_get_trades(mock_equity_curve_with_trades):
    """Tests that trade strings are parsed correctly into a DataFrame."""
    trades = utils.get_trades(mock_equity_curve_with_trades)
    assert len(trades) == 4
    assert list(trades.columns) == ['Date', 'Direction', 'Quantity', 'Ticker', 'Unit Price']
    # Check the first and last trade details
    assert trades.iloc[0]['Ticker'] == 'AAPL'
    assert trades.iloc[0]['Quantity'] == 10
    assert trades.iloc[-1]['Ticker'] == 'MSFT'
    assert trades.iloc[-1]['Direction'] == 'SELL'

def test_get_trades_no_trades(mock_equity_curve_simple):
    """Tests behavior when the order column is missing or empty."""
    # Case 1: 'order' column is missing
    df_no_order_col = mock_equity_curve_simple.copy()
    if 'order' in df_no_order_col.columns:
        df_no_order_col = df_no_order_col.drop(columns=['order'])
    assert utils.get_trades(df_no_order_col).empty

    # Case 2: 'order' column exists but is empty
    df_empty_order = mock_equity_curve_simple.copy()
    df_empty_order['order'] = ''
    assert utils.get_trades(df_empty_order).empty

def test_book_trades_long_trade(mock_trades_df):
    """Tests a simple BUY-SELL (long) trade PnL calculation."""
    # Only AAPL trades: BUY 10 @ $150, SELL 5 @ $155
    aapl_trades = mock_trades_df[mock_trades_df['Ticker'] == 'AAPL']
    closed_trades = utils.book_trades(aapl_trades)
    assert len(closed_trades) == 1
    trade = closed_trades.iloc[0]
    assert trade['Ticker'] == 'AAPL'
    assert trade['PnL'] == pytest.approx(25.0) # (155 - 150) * 5
    assert trade['Return'] == pytest.approx((5 / 150) * 100)

def test_book_trades_short_trade(mock_trades_df):
    """Tests a simple SELL-BUY (short) trade PnL calculation."""
    # Only MSFT trades: SELL 10 @ $300, BUY 10 @ $290
    msft_trades = mock_trades_df[mock_trades_df['Ticker'] == 'MSFT']
    closed_trades = utils.book_trades(msft_trades)
    assert len(closed_trades) == 1
    trade = closed_trades.iloc[0]
    assert trade['Ticker'] == 'MSFT'
    assert trade['PnL'] == pytest.approx(100.0) # (300 - 290) * 10
    assert trade['Return'] == pytest.approx((10 / 300) * 100)

def test_book_trades_no_closed_trades():
    """Tests that no trades are booked if there are only open positions."""
    open_trades_data = {
        "Date": pd.to_datetime(["2023-01-01", "2023-01-02"]),
        "Direction": ["BUY", "BUY"],
        "Quantity": [10, 5],
        "Ticker": ["AAPL", "AAPL"],
        "Unit Price": ["$150.0", "$152.0"]
    }
    open_trades_df = pd.DataFrame(open_trades_data)
    assert utils.book_trades(open_trades_df).empty

def test_get_historical_var(mock_equity_curve_with_drawdown):
    """Tests the historical Value at Risk calculation."""
    returns = mock_equity_curve_with_drawdown['returns'].dropna()
    expected_var = abs(returns.quantile(0.05) * 100)
    assert utils.get_historical_var(mock_equity_curve_with_drawdown, 0.95) == pytest.approx(expected_var)

def test_get_parametric_var(mock_equity_curve_with_drawdown):
    """Tests the parametric Value at Risk calculation."""
    returns = mock_equity_curve_with_drawdown['returns'].dropna()
    mean = returns.mean()
    std = returns.std()
    z_score = norm.ppf(0.05) # Corresponds to 95% confidence
    expected_var = abs((mean + z_score * std) * 100)
    assert utils.get_parametric_var(mock_equity_curve_with_drawdown, 0.95) == pytest.approx(expected_var)

def test_var_no_returns(mock_equity_curve_simple):
    """Tests that VaR functions return 0.0 if there are not enough returns."""
    df_no_returns = mock_equity_curve_simple.copy()
    df_no_returns['returns'] = np.nan
    assert utils.get_historical_var(df_no_returns) == 0.0
    assert utils.get_parametric_var(df_no_returns) == 0.0

def test_rolling_sharpe(mock_long_equity_curve):
    """Tests the rolling Sharpe calculation against a manual calculation."""
    window = 63  # Corresponds to '3M'
    interval = "1d"
    
    # Manually calculate the Sharpe for the last window
    returns_window = mock_long_equity_curve["returns"].dropna().tail(window)
    annualization_factor = utils.get_annualization_factor(interval)
    mean_return = np.mean(returns_window)
    std_dev = np.std(returns_window, ddof=1)
    expected_sharpe = np.sqrt(annualization_factor) * (mean_return / std_dev)
    
    # Get the series from the function
    rolling_sharpe_series = utils.rolling_sharpe(mock_long_equity_curve, interval, "3M")
    
    assert isinstance(rolling_sharpe_series, pd.Series)
    # Check the last calculated value
    assert rolling_sharpe_series.iloc[-1] == pytest.approx(expected_sharpe)

def test_rolling_volatility(mock_long_equity_curve):
    """Tests the rolling volatility calculation against a manual calculation."""
    window = 63  # Corresponds to '3M'
    interval = "1d"

    # Manually calculate volatility for the last window
    returns_window = mock_long_equity_curve["returns"].dropna().tail(window)
    annualization_factor = utils.get_annualization_factor(interval)
    expected_volatility = np.sqrt(annualization_factor) * np.std(returns_window, ddof=1)

    # Get the series from the function
    rolling_vol_series = utils.rolling_volatility(mock_long_equity_curve, interval, "3M")

    assert isinstance(rolling_vol_series, pd.Series)
    # Check the last calculated value
    assert rolling_vol_series.iloc[-1] == pytest.approx(expected_volatility)

def test_returns_histogram(mock_long_equity_curve):
    """Tests the data processing of the returns histogram function."""
    data, kurtosis, skewness = utils.returns_histogram(mock_long_equity_curve, "1d", "Weekly")
    
    # Manually calculate expected values
    resampled_df = mock_long_equity_curve["equity_curve"].resample("W").ohlc()
    resampled_df["returns"] = ((resampled_df["close"] - resampled_df["open"]) / resampled_df["open"]) * 100
    expected_kurtosis = resampled_df["returns"].kurtosis()
    expected_skewness = resampled_df["returns"].skew()

    assert isinstance(data, pd.DataFrame)
    assert "returns" in data.columns
    assert kurtosis == pytest.approx(expected_kurtosis)
    assert skewness == pytest.approx(expected_skewness)

def test_calculate_drawdowns(mock_equity_curve_with_drawdown):
    """Tests the main drawdown calculation logic."""
    analysis_df = utils.calculate_drawdowns(mock_equity_curve_with_drawdown)
    assert "drawdown_percent" in analysis_df.columns
    assert "underwater" in analysis_df.columns
    # On the day of the trough, it should be underwater
    trough_date = pd.to_datetime("2023-01-05")
    assert analysis_df.loc[trough_date, "underwater"]
    # The drawdown should be negative
    assert analysis_df.loc[trough_date, "drawdown_percent"] < 0

def test_find_top_drawdowns(mock_equity_curve_with_drawdown):
    """Tests that the function correctly identifies and summarizes the top drawdown."""
    # First, calculate the drawdown details
    analysis_df = utils.calculate_drawdowns(mock_equity_curve_with_drawdown)
    top_drawdowns = utils.find_top_drawdowns(analysis_df, n=1)
    assert len(top_drawdowns) == 1
    drawdown = top_drawdowns.iloc[0]
    assert drawdown["Peak Date"] == "03 Jan, 2023"
    assert drawdown["Trough Date"] == "05 Jan, 2023"
    assert drawdown["Recovery Date"] == "07 Jan, 2023"
    assert drawdown["Max Drawdown %"] == "-16.67%"

def test_find_top_drawdowns_no_drawdown(mock_equity_curve_simple):
    """Tests that no drawdowns are found when none exist."""
    analysis_df = utils.calculate_drawdowns(mock_equity_curve_simple)
    top_drawdowns = utils.find_top_drawdowns(analysis_df)
    assert top_drawdowns.empty

def test_returns_heatmap(mock_long_equity_curve):
    """Tests the data processing and structure of the returns heatmap."""
    heatmap_df = utils.returns_heatmap(mock_long_equity_curve, "1d", "Monthly")

    # 1. Verify structure
    assert isinstance(heatmap_df, pd.DataFrame)
    assert heatmap_df.index.name == "year"
    # The mock data is all in 2023
    assert list(heatmap_df.index) == [2023]
    # The mock data spans Jan, Feb, Mar
    assert list(heatmap_df.columns) == ["Jan", "Feb", "Mar"]

    # 2. Validate a data point (January 2023)
    jan_data = mock_long_equity_curve[mock_long_equity_curve.index.month == 1]
    jan_open = jan_data["equity_curve"].iloc[0]
    jan_close = jan_data["equity_curve"].iloc[-1]
    expected_jan_return = ((jan_close - jan_open) / jan_open) * 100
    
    # The function uses millify, so we should compare against the millified value
    expected_millified_return = float(millify(expected_jan_return, precision=2))
    
    assert heatmap_df.loc[2023, "Jan"] == pytest.approx(expected_millified_return)