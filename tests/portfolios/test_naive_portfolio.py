from collections import deque
from copy import deepcopy
from queue import Queue
from types import SimpleNamespace
from unittest.mock import MagicMock

import pandas as pd
import pytest

from backtester.enums.direction_type import DirectionType
from backtester.enums.signal_type import SignalType
from backtester.enums.order_type import OrderType
from backtester.events.event import Event
from backtester.events.fill_event import FillEvent
from backtester.events.market_event import MarketEvent
from backtester.events.signal_event import SignalEvent
from backtester.events.order_event import OrderEvent
from backtester.exceptions.negative_cash_exception import NegativeCashException
from backtester.portfolios.naive_portfolio import NaivePortfolio
from backtester.util.position_sizer.no_position_sizer import NoPositionSizer

# --- Mocks and Fixtures ---

class FakeDataHandler:
    def __init__(self, bars_map):
        self._bars = bars_map

    def get_latest_bars(self, ticker, n=1):
        return [i for idx, i in enumerate(self._bars.get(ticker, [])) if idx < n]

    def on_market(self):
        for val in self._bars.values():
            if val:
                val.popleft()

@pytest.fixture
def mock_data_handler():
    bars = {
        "MSFT": deque([
            SimpleNamespace(Index=pd.to_datetime("2023-01-01 10:00:00"), open=100, close=105),
            SimpleNamespace(Index=pd.to_datetime("2023-01-02 10:00:00"), open=105, close=115)
            ]),
        "AAPL": deque([
            SimpleNamespace(Index=pd.to_datetime("2023-01-01 10:00:00"), open=150, close=155),
            SimpleNamespace(Index=pd.to_datetime("2023-01-02 10:00:00"), open=155, close=156)
        ]),
    }
    return FakeDataHandler(bars)

@pytest.fixture
def mock_risk_manager():
    rm = MagicMock()
    rm.is_allowed.return_value = True
    return rm

@pytest.fixture
def portfolio(mock_data_handler, mock_risk_manager):
    """Returns a NaivePortfolio instance with default settings and populated history."""
    events = Queue()
    position_sizer = NoPositionSizer({"constant_position_size": 100})
    
    pf = NaivePortfolio(
        cash_buffer=1.0,
        initial_capital=100000.0,
        initial_position_size=100,
        symbol_list=["MSFT", "AAPL"],
        rounding_list=[2, 2],
        events=events,
        start_date=pd.to_datetime("2023-01-01").timestamp(),
        interval="1d",
        metrics_interval="1d",
        position_sizer=position_sizer,
        strategy_name="TestStrat",
        risk_manager=mock_risk_manager,
        maintenance_margin=0.5,
        borrow_cost=0.01
    )
    
    # Pre-populate history so generic tests don't crash on key lookup
    pf.history = {
        ("MSFT", "1d"): [SimpleNamespace(Index=pd.to_datetime("2023-01-01"), close=100)],
        ("AAPL", "1d"): [SimpleNamespace(Index=pd.to_datetime("2023-01-01"), close=150)]
    }
    return pf

# --- Test Cases ---

def test_initialization(portfolio):
    """Tests that the portfolio is initialized with correct values."""
    assert portfolio.initial_capital == 100000.0
    assert portfolio.symbol_list == ["MSFT", "AAPL"]
    assert portfolio.current_holdings["cash"] == 100000.0
    assert portfolio.current_holdings["total"] == 100000.0
    assert portfolio.current_holdings["MSFT"]["position"] == 0
    assert len(portfolio.historical_holdings) == 0

def test_on_market(portfolio):
    """Tests the behavior of the on_market method."""
    initial_holdings = deepcopy(portfolio.current_holdings)
    
    # Ensure history has data for the loop in on_market
    portfolio.history = {
        ("MSFT", "1d"): [SimpleNamespace(Index=pd.to_datetime("2023-01-02"), close=105)],
        ("AAPL", "1d"): [SimpleNamespace(Index=pd.to_datetime("2023-01-02"), close=155)]
    }

    portfolio.on_market()

    assert len(portfolio.historical_holdings) == 1
    assert portfolio.current_holdings["timestamp"] == pd.to_datetime("2023-01-02")
    # Check that state is carried over, but event-specific fields are reset
    assert portfolio.current_holdings["cash"] == initial_holdings["cash"]
    assert portfolio.current_holdings["commissions"] == 0.0
    assert portfolio.current_holdings["borrow_costs"] == 0.0
    assert portfolio.current_holdings["order"] == ""

def test_accounting_user_scenario_short_sell(mock_risk_manager):
    """
    Specific User Scenario:
    1. Start with 1 AAPL, $0 Cash.
    2. Sell 2 AAPL @ $10.
    3. Verify: Cash=$5, Equity/Total=$10, Margin=$15.
    """
    events = Queue()
    ps = NoPositionSizer({"constant_position_size": 1})
    
    pf = NaivePortfolio(
        cash_buffer=1.0,
        initial_capital=10.0, 
        initial_position_size=1,
        symbol_list=["AAPL"],
        rounding_list=[2],
        events=events,
        start_date=1000,
        interval="1d",
        metrics_interval="1d",
        position_sizer=ps,
        strategy_name="Test",
        risk_manager=mock_risk_manager,
        maintenance_margin=0.5 # 1.5x requirement
    )
    
    # Initialize history
    pf.history = {("AAPL", "1d"): [SimpleNamespace(Index=1, close=10.0)]}

    # --- Step 1: Establish Initial State (1 AAPL, $0 Cash) ---
    fill_buy = FillEvent(1, "AAPL", "EXCH", 1, DirectionType.BUY, 10.0, 10.0, commission=0)
    pf.on_fill(fill_buy)
    
    assert pf.current_holdings["AAPL"]["position"] == 1
    assert pf.current_holdings["cash"] == 0.0
    assert pf.current_holdings["total"] == 10.0

    # --- Step 2: The Short Transaction ---
    fill_sell = FillEvent(2, "AAPL", "EXCH", 2, DirectionType.SELL, 20.0, 10.0, commission=0)
    pf.on_fill(fill_sell)

    # --- Step 3: Verification ---
    assert pf.current_holdings["AAPL"]["position"] == -1.0
    assert pf.current_holdings["AAPL"]["value"] == -10.0
    
    # Margin check: abs(-10) * 1.5 = 15
    expected_margin = 15.0
    assert pf.margin_holdings["AAPL"] == expected_margin

    # Cash check: Should be $5
    # Calculation: (Start 0) + (Proceeds 20) - (Margin Locked 15) = 5
    assert pf.current_holdings["cash"] == 5.0
    
    # Total Equity check: Should be $10
    assert pf.current_holdings["total"] == 10.0

def test_end_of_day_short_mark_to_market(mock_risk_manager):
    """Tests that margin adjusts when price moves against a short position."""
    pf = NaivePortfolio(
        cash_buffer=1.0, initial_capital=100000.0, initial_position_size=100,
        symbol_list=["AAPL"], rounding_list=[2], events=Queue(), start_date=1000,
        interval="1d", metrics_interval="1d", 
        position_sizer=NoPositionSizer({"constant_position_size": 100}),
        strategy_name="Test", risk_manager=mock_risk_manager, maintenance_margin=0.5,
        borrow_cost=0.01 # 1% annual
    )

    # Update history: Price went up from 150 to 160
    pf.history = {("AAPL", "1d"): [SimpleNamespace(Index=pd.Timestamp("2023-01-01"), close=160)]}
    
    # Setup existing short: -100 AAPL @ 150
    pf.current_holdings["AAPL"]["position"] = -100
    pf.current_holdings["AAPL"]["value"] = -15000 # Old value based on 150
    pf.margin_holdings["AAPL"] = 22500 # Old margin (15k * 1.5)
    pf.current_holdings["cash"] = 92500 
    
    pf.end_of_day()
    
    # New Value: -100 * 160 = -16,000
    assert pf.current_holdings["AAPL"]["value"] == -16000
    
    # New Margin Req: 16,000 * 1.5 = 24,000
    # Margin Diff: 22,500 (old) - 24,000 (new) = -1,500 needed from cash
    
    # Borrow Cost: abs(16000) * (0.01 / 252) approx 0.63
    daily_rate = 0.01 / 252.0
    borrow_cost = 16000 * daily_rate
    
    # Cash Logic: 92,500 + (-1500 margin adjustment) - borrow_cost
    expected_cash = 92500 - 1500 - borrow_cost
    assert pf.current_holdings["cash"] == pytest.approx(expected_cash)
    
    # Margin Holdings should update
    assert pf.margin_holdings["AAPL"] == 24000
    
    # Total Logic: Cash + Margin + Value (negative)
    expected_total = expected_cash + 24000 - 16000
    assert pf.current_holdings["total"] == pytest.approx(expected_total)

def test_liquidate_short_position(mock_risk_manager):
    """Tests liquidating a short position releases margin back to cash."""
    pf = NaivePortfolio(
        cash_buffer=1.0, initial_capital=100000.0, initial_position_size=100,
        symbol_list=["AAPL"], rounding_list=[2], events=Queue(), start_date=1000,
        interval="1d", metrics_interval="1d", 
        position_sizer=NoPositionSizer({"constant_position_size": 100}),
        strategy_name="Test", risk_manager=mock_risk_manager
    )
    
    pf.history = {("AAPL", "1d"): [SimpleNamespace(Index=pd.Timestamp("2023-01-01"), close=150)]}
    
    # Setup existing short
    pf.current_holdings["AAPL"]["position"] = -100
    pf.margin_holdings["AAPL"] = 22500
    pf.current_holdings["cash"] = 92500
    pf.current_holdings["margin"]["AAPL"] = 22500
    
    pf.liquidate()
    
    # Positions cleared
    assert pf.current_holdings["AAPL"]["position"] == 0
    assert pf.margin_holdings["AAPL"] == 0
    
    # Cash logic in liquidate:
    # Cash (92500) + Margin Released (22500) = 115,000
    # Cash += Position (-100) * Close (150) -> Cash += -15000 (cost to buy back)
    # Net: 115,000 - 15,000 = 100,000
    assert pf.current_holdings["cash"] == 100000.0
    assert pf.current_holdings["total"] == 100000.0

def test_on_signal_sizing(portfolio):
    """Tests that on_signal uses the position sizer correctly."""
    # Mock position sizer to return specific quantity
    portfolio.position_sizer.get_position_size = MagicMock(return_value=50)
    
    # Ensure history exists for "MSFT" so sizing logic doesn't return early/crash
    portfolio.history = {("MSFT", "1d"): [SimpleNamespace(Index=1, close=100)]}
    
    # SignalEvent requires: (strategy_id, ticker, timestamp, signal_type, strength)
    timestamp = 1234567890
    signal = SignalEvent(1, "MSFT", timestamp, SignalType.LONG, 1.0)
    
    portfolio.on_signal(signal)
    
    assert not portfolio.events.empty()
    order = portfolio.events.get()
    
    assert order.ticker == "MSFT"
    assert order.direction == DirectionType.BUY
    assert order.quantity == 50
    portfolio.position_sizer.get_position_size.assert_called()

def test_negative_cash_exception(portfolio):
    """Tests that on_market raises exception if cash is negative."""
    portfolio.current_holdings["cash"] = -100.0
    
    # Must populate history for ALL symbols in portfolio.symbol_list ("MSFT", "AAPL")
    portfolio.history = {
        ("MSFT", "1d"): [SimpleNamespace(Index=1, close=100)],
        ("AAPL", "1d"): [SimpleNamespace(Index=1, close=150)]
    }
    
    with pytest.raises(NegativeCashException):
        portfolio.on_market()

def test_on_fill_multiple_tickers(portfolio):
    """Tests updating holdings after fills for multiple tickers."""
    opening_msft_price = 100
    quantity_msft = 100

    # First fill: BUY MSFT
    # Explicitly set commission=0 to ensure math matches expectation exactly
    fill_msft = FillEvent(123, "MSFT", "ARCA", quantity_msft, DirectionType.BUY, quantity_msft*opening_msft_price, opening_msft_price, commission=0.0)
    portfolio.on_fill(fill_msft)

    assert portfolio.current_holdings["MSFT"]["position"] == quantity_msft
    assert portfolio.current_holdings["cash"] == 100000 - 10000 # 90000
    assert portfolio.current_holdings["order"] == f"BUY {quantity_msft} MSFT @ {opening_msft_price:.2f} | "

    cash_after_msft = portfolio.current_holdings["cash"] # 90000

    opening_aapl_price = 150
    quantity_aapl = 50

    # Second fill: BUY AAPL
    fill_aapl = FillEvent(124, "AAPL", "ARCA", quantity_aapl, DirectionType.BUY, quantity_aapl*opening_aapl_price, opening_aapl_price, commission=0.0)
    portfolio.on_fill(fill_aapl)

    assert portfolio.current_holdings["AAPL"]["position"] == quantity_aapl
    assert portfolio.current_holdings["cash"] == cash_after_msft - (50 * 150) # 90000 - 7500 = 82500
    
    # Order string concatenation check
    expected_order_str = f"BUY {quantity_msft} MSFT @ {opening_msft_price:.2f} | BUY {quantity_aapl} AAPL @ {opening_aapl_price:.2f} | "
    assert portfolio.current_holdings["order"] == expected_order_str

def test_signal_flip_long_to_short(portfolio):
    """
    Tests logic when receiving a SHORT signal while currently LONG.
    The system should sell existing long position + sell new short quantity.
    """
    portfolio.position_sizer.get_position_size = MagicMock(return_value=50)
    portfolio.history = {("MSFT", "1d"): [SimpleNamespace(Index=1, close=100)]}
    
    # 1. Setup: Currently Long 100 MSFT (Value $10,000)
    portfolio.current_holdings["MSFT"]["position"] = 100
    
    # Low cash. 
    # To short 50 shares (Value $5000), we need $7500 Margin (at 1.5x).
    # Closing the Long releases $10,000 proceeds.
    # $10,000 + $1000 (start) = $11,000 Cash Available.
    # $11,000 > $7,500 Margin Requirement. 
    portfolio.current_holdings["cash"] = 1000.0 

    # 2. Signal: SHORT
    signal = SignalEvent(1, "MSFT", 12345, SignalType.SHORT, 1.0)
    portfolio.on_signal(signal)
    
    order = portfolio.events.get()
    
    # 3. Assertions
    assert order.direction == DirectionType.SELL
    # Quantity = Target (50) + Current Long (100) = 150
    assert order.quantity == 150.0 

def test_on_signal_no_data(portfolio):
    """Tests that on_signal handles missing history gracefully (no crash)."""
    # Initialize the key with an empty list
    portfolio.history = {("MSFT", "1d"): []}
    
    signal = SignalEvent(1, "MSFT", 12345, SignalType.LONG, 1.0)
    portfolio.on_signal(signal)
    
    # Should simply return without generating events or crashing
    assert portfolio.events.empty()


def test_flip_long_to_short_standard(portfolio):
    """
    Standard Flip: Long 50 -> Signal Short (Target 100).
    Condition `50 < 100` is True.
    Expected: Sell 150.
    """
    portfolio.position_sizer.get_position_size = MagicMock(return_value=100)
    portfolio.history = {("MSFT", "1d"): [SimpleNamespace(Index=1, close=100)]}
    
    # Setup: Long 50
    portfolio.current_holdings["MSFT"]["position"] = 50
    portfolio.current_holdings["cash"] = 100000 

    signal = SignalEvent(1, "MSFT", 12345, SignalType.SHORT, 1.0)
    portfolio.on_signal(signal)
    
    order = portfolio.events.get()
    
    # Logic: 100 (target) + 50 (current) = 150.
    assert order.direction == DirectionType.SELL
    assert order.quantity == 150.0

def test_flip_large_long_to_small_short(portfolio):
    """
    Regression Test for Logic Bug: Long 100 -> Signal Short (Target 20).
    Condition `100 < 20` is FALSE. Code currently skips logic.
    Expected: Sell 120 (Close 100, Open 20).
    """
    portfolio.position_sizer.get_position_size = MagicMock(return_value=20)
    portfolio.history = {("MSFT", "1d"): [SimpleNamespace(Index=1, close=100)]}
    
    # Setup: Long 100
    portfolio.current_holdings["MSFT"]["position"] = 100
    portfolio.current_holdings["cash"] = 100000 

    signal = SignalEvent(1, "MSFT", 12345, SignalType.SHORT, 1.0)
    portfolio.on_signal(signal)
    
    order = portfolio.events.get()
    
    assert order.direction == DirectionType.SELL
    assert order.quantity == 120.0 

def test_flip_short_to_long_any_size(portfolio):
    """
    Tests flipping from Short to Long. 
    Since negative numbers are always < positive target, this usually passes,
    but it verifies the `abs()` math is correct.
    """
    portfolio.position_sizer.get_position_size = MagicMock(return_value=20)
    portfolio.history = {("MSFT", "1d"): [SimpleNamespace(Index=1, close=100)]}
    
    # Setup: Short 100
    portfolio.current_holdings["MSFT"]["position"] = -100
    portfolio.margin_holdings["MSFT"] = 15000 
    portfolio.current_holdings["cash"] = 100000

    signal = SignalEvent(1, "MSFT", 12345, SignalType.LONG, 1.0)
    portfolio.on_signal(signal)
    
    order = portfolio.events.get()
    
    # Logic: Target 20 + Abs(-100) = 120.
    assert order.direction == DirectionType.BUY
    assert order.quantity == 120.0

def test_reduce_long_position(portfolio):
    """
    Tests reducing a position (Profit Taking).
    Current: Long 100. Signal: Long (Target 20).
    Expected: Sell 80.
    """
    portfolio.position_sizer.get_position_size = MagicMock(return_value=20)
    portfolio.history = {("MSFT", "1d"): [SimpleNamespace(Index=1, close=100)]}
    
    portfolio.current_holdings["MSFT"]["position"] = 100
    portfolio.current_holdings["cash"] = 100000 

    signal = SignalEvent(1, "MSFT", 12345, SignalType.LONG, 1.0)
    portfolio.on_signal(signal)
    
    order = portfolio.events.get()
    
    # If the sizer says "Hold 20" and we hold 100, we should Sell 80.
    # This assertion checks if the portfolio is smart enough to sell to reduce exposure.
    assert order.direction == DirectionType.SELL
    assert order.quantity == 80.0