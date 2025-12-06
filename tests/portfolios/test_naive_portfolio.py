from collections import deque
from copy import deepcopy
from queue import Queue
from types import SimpleNamespace

import pandas as pd
import pytest

from backtester.enums.direction_type import DirectionType
from backtester.enums.signal_type import SignalType
from backtester.events.event import Event
from backtester.events.fill_event import FillEvent
from backtester.events.market_event import MarketEvent
from backtester.events.signal_event import SignalEvent
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
def portfolio(mock_data_handler):
    """Returns a NaivePortfolio instance with default settings."""
    events = Queue()
    position_sizer = NoPositionSizer({"constant_position_size": 100})
    return NaivePortfolio(
        data_handler=mock_data_handler,
        initial_capital=100000.0,
        initial_position_size=100,
        symbol_list=["MSFT", "AAPL"],
        events=events,
        start_date=pd.to_datetime("2023-01-01").timestamp(),
        interval="1d",
        position_sizer=position_sizer,
    )

# --- Test Cases ---

def test_initialization(portfolio):
    """Tests that the portfolio is initialized with correct values."""
    assert portfolio.initial_capital == 100000.0
    assert portfolio.symbol_list == ["MSFT", "AAPL"]
    assert portfolio.position_dict == {"MSFT": 100, "AAPL": 100}
    assert portfolio.current_holdings["cash"] == 100000.0
    assert portfolio.current_holdings["total"] == 100000.0
    assert portfolio.current_holdings["MSFT"]["position"] == 0
    assert len(portfolio.historical_holdings) == 0


def test_on_market(portfolio):
    """Tests the behavior of the on_market method."""
    initial_holdings = deepcopy(portfolio.current_holdings)
    market_event = Event()
    market_event.type = "MARKET"
    market_event.timestamp = pd.to_datetime("2023-01-02").timestamp()

    portfolio.on_market(market_event)

    assert len(portfolio.historical_holdings) == 1
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
    events = list(portfolio.events.queue)
    assert len(events) == 1
    order = events[0]
    assert order.direction == DirectionType.BUY
    assert order.quantity == 100

def test_on_signal_short_from_long(portfolio):
    """Tests creating a SHORT order from a LONG position (exit and enter)."""
    portfolio.current_holdings["MSFT"]["position"] = 100
    signal = SignalEvent(123, "MSFT", SignalType.SHORT)
    portfolio.on_signal(signal)
    events = list(portfolio.events.queue)
    assert len(events) == 1
    order = events[0]
    assert order.direction == DirectionType.SELL
    assert order.quantity == 200 # 100 to close, 100 to open short

def test_on_signal_exit_from_long(portfolio):
    """Tests creating an EXIT order from a LONG position."""
    portfolio.current_holdings["MSFT"]["position"] = 100
    signal = SignalEvent(123, "MSFT", SignalType.EXIT)
    portfolio.on_signal(signal)
    events = list(portfolio.events.queue)
    assert len(events) == 1
    order = events[0]
    assert order.direction == DirectionType.SELL
    assert order.quantity == 100

def test_on_signal_exit_from_short(portfolio):
    """
    Tests that when exiting a short position, the resulting BUY order
    has a positive quantity.
    """
    portfolio.current_holdings["MSFT"]["position"] = -100
    signal = SignalEvent(123, "MSFT", SignalType.EXIT)
    portfolio.on_signal(signal)
    order = portfolio.events.get()
    assert order.direction == DirectionType.BUY
    assert order.quantity == 100

def test_on_fill_buy(portfolio):
    """Tests updating holdings after a BUY fill."""
    fill = FillEvent(123, "MSFT", "ARCA", 100, DirectionType.BUY, 10000, 100)
    portfolio.on_fill(fill)
    assert portfolio.current_holdings["MSFT"]["position"] == 100
    assert portfolio.current_holdings["MSFT"]["value"] == 10000 # 100 * 100 (fill price)
    assert portfolio.current_holdings["cash"] == 100000 - 10000 - fill.commission
    assert portfolio.current_holdings["total"] == 100000 - fill.commission

def test_on_fill_sell_to_close(portfolio):
    """Tests updating holdings after a SELL fill to close a long position."""
    # First, establish a long position
    portfolio.current_holdings["MSFT"]["position"] = 100
    portfolio.current_holdings["MSFT"]["value"] = 10000 # Assume bought at 100
    portfolio.current_holdings["cash"] = 90000
    portfolio.current_holdings["total"] = 100000

    fill = FillEvent(123, "MSFT", "ARCA", 100, DirectionType.SELL, 11000, 110)
    portfolio.on_fill(fill)

    assert portfolio.current_holdings["MSFT"]["position"] == 0
    assert portfolio.current_holdings["MSFT"]["value"] == 0 # Position is closed
    assert portfolio.current_holdings["cash"] == 90000 + 11000 - fill.commission
    assert portfolio.current_holdings["total"] == 100000 + 1000 - fill.commission # 1000 profit

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
    opening_msft_price = 100
    closing_msft_price = 105
    quantity_msft = 100

    # First fill: BUY MSFT
    fill_msft = FillEvent(123, "MSFT", "ARCA", quantity_msft, DirectionType.BUY, quantity_msft*opening_msft_price, opening_msft_price)
    portfolio.on_fill(fill_msft)

    assert portfolio.current_holdings["MSFT"]["position"] == quantity_msft
    assert portfolio.current_holdings["cash"] == 100000 - quantity_msft*opening_msft_price - fill_msft.commission
    assert portfolio.current_holdings["total"] == 100000 - fill_msft.commission
    assert portfolio.current_holdings["order"] == f"BUY {quantity_msft} MSFT @ {opening_msft_price}.00 | "

    cash_after_msft = portfolio.current_holdings["cash"]

    opening_aapl_price = 150
    closing_aapl_price = 155
    quantity_aapl = 50

    # Second fill: BUY AAPL
    fill_aapl = FillEvent(124, "AAPL", "ARCA", quantity_aapl, DirectionType.BUY, quantity_aapl*opening_aapl_price, opening_aapl_price)
    portfolio.on_fill(fill_aapl)

    assert portfolio.current_holdings["AAPL"]["position"] == quantity_aapl
    assert portfolio.current_holdings["cash"] == cash_after_msft - quantity_aapl*opening_aapl_price - fill_aapl.commission
    assert portfolio.current_holdings["total"] == 100000 - fill_msft.commission - fill_aapl.commission
    assert portfolio.current_holdings["order"] == f"BUY {quantity_msft} MSFT @ {opening_msft_price}.00 | BUY {quantity_aapl} AAPL @ {opening_aapl_price}.00 | "

    portfolio.end_of_interval()

    assert portfolio.current_holdings["cash"] == cash_after_msft - quantity_aapl*opening_aapl_price - fill_aapl.commission
    assert portfolio.current_holdings["total"] == portfolio.current_holdings["cash"] + quantity_msft*closing_msft_price + quantity_aapl*closing_aapl_price

def test_on_fill_with_existing_holdings(portfolio):
    """Tests updating holdings after fills for multiple tickers."""
    """Tests updating holdings after fills for multiple tickers."""
    opening_msft_price = 100
    closing_msft_price = 105
    quantity_msft = 100

    # First fill: BUY MSFT
    fill_msft = FillEvent(123, "MSFT", "ARCA", quantity_msft, DirectionType.BUY, quantity_msft*opening_msft_price, opening_msft_price)
    portfolio.on_fill(fill_msft)

    assert portfolio.current_holdings["MSFT"]["position"] == quantity_msft
    assert portfolio.current_holdings["cash"] == 100000 - quantity_msft*opening_msft_price - fill_msft.commission
    assert portfolio.current_holdings["total"] == 100000 - fill_msft.commission
    assert portfolio.current_holdings["order"] == f"BUY {quantity_msft} MSFT @ {opening_msft_price}.00 | "

    portfolio.end_of_interval()

    assert portfolio.current_holdings["cash"] == 100000 - quantity_msft*opening_msft_price - fill_msft.commission
    assert portfolio.current_holdings["total"] == portfolio.current_holdings["cash"] + quantity_msft*closing_msft_price

    cash_after_first_fill = portfolio.current_holdings["cash"]
    posiiton_after_first_fill = portfolio.current_holdings["MSFT"]["position"]
    total_after_first_fill = portfolio.current_holdings["total"]
    
    portfolio.on_market(MarketEvent(1, False))
    portfolio.data_handler.on_market()

    opening_msft_price = 105
    closing_msft_price = 115
    quantity_msft = 50

    # Second fill: BUY MSFT
    fill_msft = FillEvent(124, "MSFT", "ARCA", quantity_msft, DirectionType.BUY, quantity_msft*opening_msft_price, opening_msft_price)
    portfolio.on_fill(fill_msft)

    assert portfolio.current_holdings["MSFT"]["position"] == posiiton_after_first_fill + quantity_msft
    assert portfolio.current_holdings["cash"] == cash_after_first_fill - quantity_msft*opening_msft_price - fill_msft.commission
    assert portfolio.current_holdings["total"] == total_after_first_fill - fill_msft.commission
    assert portfolio.current_holdings["order"] == f"BUY {quantity_msft} MSFT @ {opening_msft_price}.00 | "

    portfolio.end_of_interval()

    assert portfolio.current_holdings["cash"] == cash_after_first_fill - quantity_msft*opening_msft_price - fill_msft.commission
    assert portfolio.current_holdings["total"] == portfolio.current_holdings["cash"] + portfolio.current_holdings["MSFT"]["position"]*closing_msft_price

def test_liquidate(portfolio):
    """Tests that all positions are closed and assets are converted to cash."""
    portfolio.current_holdings["MSFT"]["position"] = 100
    portfolio.current_holdings["MSFT"]["value"] = 10500
    portfolio.current_holdings["AAPL"]["position"] = -50
    portfolio.current_holdings["AAPL"]["value"] = -7750
    portfolio.margin_holdings["AAPL"] = 10000
    portfolio.current_holdings["cash"] = 50000

    portfolio.liquidate()

    assert portfolio.current_holdings["MSFT"]["position"] == 0
    assert portfolio.current_holdings["AAPL"]["position"] == 0
    
    # Cash = initial_cash + released_margin + liquidated_value
    expected_cash = 50000 + 10000 + (100 * 105) + (-50 * 155)
    assert portfolio.current_holdings["cash"] == pytest.approx(expected_cash)
    assert portfolio.current_holdings["total"] == portfolio.current_holdings["cash"]
    assert len(portfolio.historical_holdings) == 1

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

def test_on_signal_with_position_sizer(portfolio):
    """Tests that on_signal generates an order when the position sizer returns a size."""
    portfolio.position_sizer.get_position_size = lambda portfolio, ticker: 250
    signal = SignalEvent(123, "MSFT", SignalType.LONG)
    
    portfolio.on_signal(signal)
    
    assert len(portfolio.events.queue) == 1
    order = portfolio.events.queue.pop()
    assert order.quantity == 250

def test_on_signal_with_no_position_size(portfolio):
    """Tests that on_signal does nothing if the position sizer returns None."""
    portfolio.position_sizer.get_position_size = lambda portfolio, ticker: None
    signal = SignalEvent(123, "MSFT", SignalType.LONG)
    
    portfolio.on_signal(signal)
    
    assert len(portfolio.events.queue) == 1

    order = portfolio.events.queue[0]
    assert order.quantity == portfolio.initial_position_size
    assert order.direction == DirectionType.BUY