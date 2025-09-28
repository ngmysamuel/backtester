from collections import deque
from types import SimpleNamespace
import pytest
import pandas as pd
from copy import deepcopy

from backtester.portfolios.naive_portfolio import NaivePortfolio
from backtester.events.event import Event
from backtester.events.signal_event import SignalEvent
from backtester.events.fill_event import FillEvent
from backtester.enums.signal_type import SignalType
from backtester.enums.direction_type import DirectionType
from backtester.exceptions.negative_cash_exception import NegativeCashException

# --- Mocks and Fixtures ---

class FakeDataHandler:
    def __init__(self, bars_map):
        self._bars = bars_map

    def get_latest_bars(self, ticker, n=1):
        return self._bars.get(ticker, [])

@pytest.fixture
def mock_data_handler():
    bars = {
        "MSFT": [SimpleNamespace(Index=pd.to_datetime("2023-01-01 10:00:00"), open=100, close=105)],
        "AAPL": [SimpleNamespace(Index=pd.to_datetime("2023-01-01 10:00:00"), open=150, close=155)],
    }
    return FakeDataHandler(bars)

@pytest.fixture
def portfolio(mock_data_handler):
    """Returns a NaivePortfolio instance with default settings."""
    events = deque()
    return NaivePortfolio(
        data_handler=mock_data_handler,
        initial_capital=100000.0,
        symbol_list=["MSFT", "AAPL"],
        events=events,
        start_date=pd.to_datetime("2023-01-01").timestamp()
    )

# --- Test Cases ---

def test_initialization(portfolio):
    """Tests that the portfolio is initialized with correct values."""
    assert portfolio.initial_capital == 100000.0
    assert portfolio.symbol_list == ["MSFT", "AAPL"]
    assert portfolio.position_size == 100
    assert portfolio.current_holdings["cash"] == 100000.0
    assert portfolio.current_holdings["total"] == 100000.0
    assert portfolio.current_holdings["MSFT"]["position"] == 0
    assert len(portfolio.historical_holdings) == 1

def test_calc_atr_insufficient_data(portfolio):
    """Tests that _calc_atr returns None if there is not enough data."""
    # Default portfolio has atr_period=14, so needs 15 bars. mock_data_handler only provides 1.
    assert portfolio._calc_atr() is None

def test_calc_atr_correct_calculation(portfolio, mock_data_handler):
    """Tests that the ATR is calculated correctly based on mock data."""
    # Setup data for a 5-period ATR for simplicity
    portfolio.atr_period = 5
    bars = [
        SimpleNamespace(high=10, low=8, close=9),
        SimpleNamespace(high=11, low=9, close=10),
        SimpleNamespace(high=12, low=10, close=11),
        SimpleNamespace(high=13, low=11, close=12),
        SimpleNamespace(high=14, low=12, close=13),
        SimpleNamespace(high=15, low=13, close=14),
    ]
    mock_data_handler._bars["MSFT"] = bars
    
    # Expected TRs:
    # Bar 1: h-l=2, h-pc=nan, l-pc=nan -> TR = 2
    # Bar 2: h-l=2, h-pc=2, l-pc=0 -> TR = 2
    # Bar 3: h-l=2, h-pc=2, l-pc=0 -> TR = 2
    # Bar 4: h-l=2, h-pc=2, l-pc=0 -> TR = 2
    # Bar 5: h-l=2, h-pc=2, l-pc=0 -> TR = 2
    # Expected ATR = mean([2,2,2,2,2]) = 2
    assert portfolio._calc_atr() == pytest.approx(2.0)

def test_on_market_updates_position_size_with_atr(portfolio, mock_data_handler):
    """Tests that on_market correctly updates position_size based on ATR."""
    # Setup data that will produce a known ATR
    portfolio.atr_period = 5
    bars = [SimpleNamespace(high=10, low=8, close=9)] * 6
    mock_data_handler._bars["MSFT"] = bars
    
    # ATR will be 2.0. risk_per_trade=0.01, total=100000, atr_multiplier=2
    # capital_to_risk = 0.01 * 100000 = 1000
    # position_size = 1000 // (2.0 * 2) = 1000 // 4 = 250
    market_event = Event()
    market_event.type = "MARKET"
    market_event.timestamp = pd.to_datetime("2023-01-02").timestamp()
    
    portfolio.on_market(market_event)
    
    assert portfolio.position_size == 250

def test_on_market_handles_zero_atr(portfolio, mock_data_handler):
    """Tests that a ZeroDivisionError is avoided if ATR is 0."""
    portfolio.atr_period = 5
    # Data with no price movement will result in ATR=0
    bars = [SimpleNamespace(high=10, low=10, close=10)] * 6
    mock_data_handler._bars["MSFT"] = bars
    
    market_event = Event()
    market_event.type = "MARKET"
    market_event.timestamp = pd.to_datetime("2023-01-02").timestamp()

    try:
        portfolio.on_market(market_event)
    except ZeroDivisionError:
        pytest.fail("on_market raised a ZeroDivisionError due to zero ATR.")
    
    # If ATR is 0, position size should probably remain unchanged or be set to 0
    # Current implementation will keep the initial value of 100.
    assert portfolio.position_size == 100

def test_calc_atr(portfolio, mock_data_handler):
  portfolio.atr_period = 5
  portfolio.historical_atr = {"MSFT": [2]}
  bars = [
      {"high":10,"low":8,"close":9},
      {"high":11,"low":9,"close":10},
      {"high":12,"low":10,"close":11},
      {"high":13,"low":11,"close":12},
      {"high":14,"low":12,"close":13},
      {"high":15,"low":13,"close":14},
      {"high":16,"low":14,"close":15},
    ]
  mock_data_handler._bars["MSFT"] = bars
  print(portfolio._calc_atr("MSFT"))
  assert 1 == 2


def test_on_market(portfolio):
    """Tests the behavior of the on_market method."""
    initial_holdings = deepcopy(portfolio.current_holdings)
    market_event = Event()
    market_event.type = "MARKET"
    market_event.timestamp = pd.to_datetime("2023-01-02").timestamp()

    portfolio.on_market(market_event)

    assert len(portfolio.historical_holdings) == 2
    assert portfolio.current_holdings["timestamp"] == market_event.timestamp
    # Check that state is carried over, but event-specific fields are reset
    assert portfolio.current_holdings["cash"] == initial_holdings["cash"]
    assert portfolio.current_holdings["commissions"] == 0.0
    assert portfolio.current_holdings["borrow_costs"] == 0.0
    assert portfolio.current_holdings["order"] == ""

def test_on_market_raises_negative_cash_exception(portfolio):
    """Tests that on_market raises an exception if cash is negative."""
    portfolio.current_holdings["cash"] = -1.0
    market_event = Event()
    market_event.type = "MARKET"
    market_event.timestamp = pd.to_datetime("2023-01-02").timestamp()
    with pytest.raises(NegativeCashException):
        portfolio.on_market(market_event)

def test_on_signal_long_from_flat(portfolio):
    """Tests creating a LONG order from a flat position."""
    signal = SignalEvent(123, "MSFT", SignalType.LONG)
    portfolio.on_signal(signal)
    assert len(portfolio.events) == 1
    order = portfolio.events.pop()
    assert order.direction == DirectionType.BUY
    assert order.quantity == 100

def test_on_signal_short_from_long(portfolio):
    """Tests creating a SHORT order from a LONG position (exit and enter)."""
    portfolio.current_holdings["MSFT"]["position"] = 100
    signal = SignalEvent(123, "MSFT", SignalType.SHORT)
    portfolio.on_signal(signal)
    assert len(portfolio.events) == 1
    order = portfolio.events.pop()
    assert order.direction == DirectionType.SELL
    assert order.quantity == 200 # 100 to close, 100 to open short

def test_on_signal_exit_from_long(portfolio):
    """Tests creating an EXIT order from a LONG position."""
    portfolio.current_holdings["MSFT"]["position"] = 100
    signal = SignalEvent(123, "MSFT", SignalType.EXIT)
    portfolio.on_signal(signal)
    assert len(portfolio.events) == 1
    order = portfolio.events.pop()
    assert order.direction == DirectionType.SELL
    assert order.quantity == 100

def test_on_signal_exit_from_short_bug(portfolio):
    """
    This test exposes a bug. The quantity for an order should always be positive.
    When exiting a short, the current implementation passes a negative quantity.
    """
    portfolio.current_holdings["MSFT"]["position"] = -100
    signal = SignalEvent(123, "MSFT", SignalType.EXIT)
    portfolio.on_signal(signal)
    order = portfolio.events.pop()
    assert order.direction == DirectionType.BUY
    # This will fail with the current code. The quantity should be positive.
    assert order.quantity == 100

def test_on_fill_buy(portfolio):
    """Tests updating holdings after a BUY fill."""
    fill = FillEvent(123, "MSFT", "ARCA", 100, DirectionType.BUY, 10000, 5.0)
    portfolio.on_fill(fill)
    assert portfolio.current_holdings["MSFT"]["position"] == 100
    assert portfolio.current_holdings["MSFT"]["value"] == 10500 # 100 * 105 (close price)
    assert portfolio.current_holdings["cash"] == 100000 - 10000 - 5.0
    assert portfolio.current_holdings["total"] == 100000 + (10500 - 0 - 5.0)
    assert portfolio.current_holdings["commissions"] == 5.0

def test_on_fill_sell_to_close(portfolio):
    """Tests updating holdings after a SELL fill to close a long position."""
    # First, establish a long position
    portfolio.current_holdings["MSFT"]["position"] = 100
    portfolio.current_holdings["MSFT"]["value"] = 10500
    portfolio.current_holdings["cash"] = 90000
    portfolio.current_holdings["total"] = 100500

    fill = FillEvent(123, "MSFT", "ARCA", 100, DirectionType.SELL, 11000, 5.0)
    portfolio.on_fill(fill)

    assert portfolio.current_holdings["MSFT"]["position"] == 0
    assert portfolio.current_holdings["MSFT"]["value"] == 0 # 0 * 105
    assert portfolio.current_holdings["cash"] == 90000 + 11000 - 5.0
    assert portfolio.current_holdings["total"] == 100500 + (0 - 10500 - 5.0)
    assert portfolio.current_holdings["commissions"] == 5.0

def test_end_of_day_short_position(portfolio):
    """Tests margin and borrow cost calculation for a short position."""
    portfolio.current_holdings["MSFT"]["position"] = -100
    
    portfolio.end_of_day()

    assert portfolio.current_holdings["MSFT"]["value"] == -10500
    expected_margin = abs(-10500) * (1 + portfolio.maintenance_margin)
    assert portfolio.margin_holdings["MSFT"] == pytest.approx(expected_margin)
    assert portfolio.current_holdings["cash"] < 100000 # Cash is reduced by margin and borrow cost

    expected_borrow_cost = abs(-10500) * portfolio.daily_borrow_rate
    assert portfolio.current_holdings["borrow_costs"] == pytest.approx(expected_borrow_cost)
    
    # Total should be cash + value + margin
    expected_total = portfolio.current_holdings["cash"] + portfolio.current_holdings["MSFT"]["value"] + portfolio.margin_holdings["MSFT"]
    assert portfolio.current_holdings["total"] == pytest.approx(expected_total)

def test_end_of_day_mixed_positions(portfolio):
    """Tests end_of_day logic with both long and short positions."""
    # Setup: 1 long (MSFT), 1 short (AAPL), and some initial margin on MSFT to be released
    portfolio.current_holdings["MSFT"]["position"] = 100
    portfolio.current_holdings["AAPL"]["position"] = -50
    portfolio.current_holdings["cash"] = 50000
    portfolio.margin_holdings["MSFT"] = 2000  # Margin that should be released

    portfolio.end_of_day()

    # Assertions for MSFT (Long Position)
    assert portfolio.current_holdings["MSFT"]["value"] == 10500
    assert portfolio.margin_holdings["MSFT"] == 0  # Margin released

    # Assertions for AAPL (Short Position)
    assert portfolio.current_holdings["AAPL"]["value"] == -7750
    expected_aapl_margin = abs(-7750) * (1 + portfolio.maintenance_margin)
    assert portfolio.margin_holdings["AAPL"] == pytest.approx(expected_aapl_margin)
    
    expected_borrow_cost = abs(-7750) * portfolio.daily_borrow_rate
    assert portfolio.current_holdings["borrow_costs"] == pytest.approx(expected_borrow_cost)

    # Assertions for Cash
    expected_cash = 50000 + 2000 - portfolio.margin_holdings["AAPL"] - portfolio.current_holdings["borrow_costs"]
    assert portfolio.current_holdings["cash"] == pytest.approx(expected_cash)

    # Verify the internal consistency of the final total.
    final_cash = portfolio.current_holdings["cash"]
    total_position_value = sum(portfolio.current_holdings[s]["value"] for s in portfolio.symbol_list)
    total_margin_held = sum(portfolio.margin_holdings.values())
    
    expected_total = final_cash + total_position_value + total_margin_held
    assert portfolio.current_holdings["total"] == pytest.approx(expected_total)

def test_end_of_day_long_position_releases_margin(portfolio):
    """Tests that held margin is released when a position becomes long."""
    portfolio.margin_holdings["MSFT"] = 5000
    portfolio.current_holdings["MSFT"]["position"] = 100
    portfolio.current_holdings["MSFT"]["value"] = 10500
    portfolio.current_holdings["cash"] = 80000

    portfolio.end_of_day()

    assert portfolio.margin_holdings["MSFT"] == 0
    assert portfolio.current_holdings["cash"] == 85000 # 80000 + 5000 released margin
    assert portfolio.current_holdings["total"] == 85000 + 10500

def test_on_fill_multiple_tickers(portfolio):
    """Tests updating holdings after fills for multiple tickers."""
    # First fill: BUY MSFT
    fill_msft = FillEvent(123, "MSFT", "ARCA", 100, DirectionType.BUY, 10000, 5.0)
    portfolio.on_fill(fill_msft)

    assert portfolio.current_holdings["MSFT"]["position"] == 100
    assert portfolio.current_holdings["cash"] == 90000 - 5.0
    assert portfolio.current_holdings["total"] == 100000 + (10500 - 0 - 5.0)

    # Second fill: BUY AAPL
    fill_aapl = FillEvent(124, "AAPL", "ARCA", 50, DirectionType.BUY, 7500, 5.0)
    portfolio.on_fill(fill_aapl)

    assert portfolio.current_holdings["AAPL"]["position"] == 50
    assert portfolio.current_holdings["cash"] == 90000 - 5.0 - 7500 - 5.0
    # total = initial_total + (msft_value - msft_commission) + (aapl_value - aapl_commission)
    assert portfolio.current_holdings["total"] == 100000 + (10500 - 5.0) + (50 * 155 - 5.0)

def test_liquidate(portfolio):
    """Tests that all positions are closed and assets are converted to cash."""
    portfolio.current_holdings["MSFT"]["position"] = 100
    portfolio.current_holdings["MSFT"]["value"] = 10500
    portfolio.current_holdings["AAPL"]["position"] = -50
    portfolio.current_holdings["AAPL"]["value"] = -7750
    portfolio.margin_holdings["AAPL"] = 10000
    portfolio.current_holdings["cash"] = 50000
    # This is the fix: initialize the 'margin' dictionary
    portfolio.current_holdings["margin"] = {"MSFT": 0, "AAPL": 10000}

    portfolio.liquidate()

    assert portfolio.current_holdings["MSFT"]["position"] == 0
    assert portfolio.current_holdings["AAPL"]["position"] == 0
    
    # Cash = initial_cash + released_margin + liquidated_value
    expected_cash = 50000 + 10000 + (100 * 105) + (-50 * 155)
    assert portfolio.current_holdings["cash"] == pytest.approx(expected_cash)
    assert portfolio.current_holdings["total"] == portfolio.current_holdings["cash"]
    assert len(portfolio.historical_holdings) == 2

def test_create_equity_curve(portfolio):
    """Tests the creation and structure of the equity curve DataFrame."""
    # Add some history
    portfolio.historical_holdings.append({'total': 101000.0, 'timestamp': pd.to_datetime("2023-01-02").timestamp()})
    portfolio.historical_holdings.append({'total': 100500.0, 'timestamp': pd.to_datetime("2023-01-03").timestamp()})
    
    portfolio.create_equity_curve()
    
    curve = portfolio.equity_curve
    assert isinstance(curve, pd.DataFrame)
    assert isinstance(curve.index, pd.DatetimeIndex)
    assert "returns" in curve.columns
    assert "equity_curve" in curve.columns
    assert curve["equity_curve"].iloc[-1] < curve["equity_curve"].iloc[-2]