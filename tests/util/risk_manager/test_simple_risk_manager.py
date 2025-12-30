import time
import pytest
import collections
from backtester.enums.direction_type import DirectionType
from backtester.enums.order_type import OrderType
from backtester.events.order_event import OrderEvent
from backtester.util.util import BarTuple
from backtester.util.risk_manager.simple_risk_manager import SimpleRiskManager

# --- SETUP ---

@pytest.fixture
def risk_manager():
    # We set strict limits here, but since we call private methods directly,
    # we don't need to worry about one limit interfering with another.
    config = {
        "max_order_quantity": 100,
        "max_notional_value": 10000.0,
        "max_daily_loss": 0.05,
        "max_gross_exposure": 50000.0,
        "max_net_exposure": 25000.0,
        "participation_window": 5,
        "participation_limit": 0.1,
        "rate_limit": 2
    }
    return SimpleRiskManager(config)

@pytest.fixture
def basic_order():
    return OrderEvent(DirectionType.BUY, "AAPL", "TestStrat", OrderType.MKT, 10, time.time())

@pytest.fixture
def holdings():
    return {
        "total": 100000.0,
        "AAPL": {"value": 20000.0, "position": 200},
        "MSFT": {"value": 0.0, "position": 0}
    }

@pytest.fixture
def history():
    # Price 100, Volume 1000
    return [BarTuple(time.time(), 100, 100, 100, 100, 1000, None) for _ in range(5)]


# --- INDIVIDUAL METHOD TESTS ---

def test_check_max_order_quantity(risk_manager, basic_order):
    """Test _max_order_quantity_check directly"""
    
    # 1. Valid Case
    basic_order.quantity = 100
    # Should not raise exception
    risk_manager._max_order_quantity_check(basic_order)

    # 2. Invalid Case
    basic_order.quantity = 101
    with pytest.raises(ValueError, match="Max Order Quantity check failed"):
        risk_manager._max_order_quantity_check(basic_order)


def test_check_max_notional_value(risk_manager, basic_order):
    """Test _max_notional_value_check directly"""
    price = 100.0
    
    # 1. Valid Case ($10,000)
    basic_order.quantity = 100
    risk_manager._max_notional_value_check(basic_order, price)

    # 2. Invalid Case ($10,100)
    basic_order.quantity = 101
    with pytest.raises(ValueError, match="Max Notional Value check failed"):
        risk_manager._max_notional_value_check(basic_order, price)


def test_check_daily_loss_limit(risk_manager, basic_order, holdings):
    """Test _daily_loss_limit_check directly"""
    # Config Limit is 5%
    
    # Scenario: We are down 10%
    holdings["total"] = 90000.0 
    open_value = 100000.0
    
    # 1. Valid Case: Hedging (Reducing position)
    # Long Position, Selling
    basic_order.direction = DirectionType.SELL
    risk_manager._daily_loss_limit_check(basic_order, holdings, open_value)

    # 2. Invalid Case: Adding to Loser
    # Long Position, Buying
    basic_order.direction = DirectionType.BUY
    with pytest.raises(ValueError, match="Daily loss limit failed"):
        risk_manager._daily_loss_limit_check(basic_order, holdings, open_value)


def test_check_gross_exposure(risk_manager, basic_order, holdings):
    """Test _gross_exposure_check directly"""
    # Limit: 50,000
    # Current Exposure: 20,000 (AAPL)
    price = 100.0
    
    # 1. Valid Case: Buy 200 ($20k). New Gross = 40k < 50k
    basic_order.quantity = 200
    risk_manager._gross_exposure_check(basic_order, ["AAPL", "MSFT"], holdings, price)

    # 2. Invalid Case: Buy 400 ($40k). New Gross = 60k > 50k
    basic_order.quantity = 400
    with pytest.raises(ValueError, match="Gross Exposure check failed"):
        risk_manager._gross_exposure_check(basic_order, ["AAPL", "MSFT"], holdings, price)


def test_check_net_exposure(risk_manager, basic_order, holdings):
    """Test _net_exposure_check directly"""
    # Limit: 25,000
    # Current Net: +20,000
    price = 100.0
    
    # 1. Valid Case: Buy 50 ($5k). New Net = +25k. OK.
    basic_order.quantity = 50
    risk_manager._net_exposure_check(basic_order, ["AAPL", "MSFT"], holdings, price)

    # 2. Invalid Case (Upside): Buy 51 ($5.1k). New Net = +25.1k. Fail.
    basic_order.quantity = 51
    with pytest.raises(ValueError, match="Net Exposure check failed"):
        risk_manager._net_exposure_check(basic_order, ["AAPL", "MSFT"], holdings, price)

    # 3. Invalid Case (Downside/Short): Sell 500 ($50k).
    # Current 20k - 50k = -30k Net. Abs(-30k) > 25k. Fail.
    basic_order.direction = DirectionType.SELL
    basic_order.quantity = 500
    with pytest.raises(ValueError, match="Net Exposure check failed"):
        risk_manager._net_exposure_check(basic_order, ["AAPL", "MSFT"], holdings, price)


def test_check_participation(risk_manager, basic_order):
    """Test _participation_check directly"""
    # Limit: 10%
    
    # 1. Valid Case (Standard Volume)
    # History: 1000 vol. Max Order = 100.
    history_normal = [BarTuple(time.time(), 100, 100, 100, 100, 1000, None) for _ in range(5)]
    basic_order.quantity = 100
    risk_manager._participation_check(basic_order, history_normal)

    # 2. Invalid Case (Exceeds %)
    basic_order.quantity = 101
    with pytest.raises(ValueError, match="participation check failed"):
        risk_manager._participation_check(basic_order, history_normal)

    # 3. Invalid Case (Zero Volume)
    history_zero = [BarTuple(time.time(), 100, 100, 100, 100, 0, None) for _ in range(5)]
    basic_order.quantity = 10
    with pytest.raises(ValueError, match="zero volume"):
        risk_manager._participation_check(basic_order, history_zero)


def test_check_rate_limit(risk_manager):
    """Test _rate_limit_check directly"""
    # Limit: 2 orders per second
    
    # Fill the deque manually to simulate state
    now = time.time()
    risk_manager.order_timestamps = collections.deque([now, now, now])
    
    # 1. Invalid Case: We already have 2 orders. The 3rd check should fail.
    with pytest.raises(ValueError, match="Rate limit check failed"):
        risk_manager._rate_limit_check()
        
    # 2. Valid Case: Time passes, window clears
    risk_manager.order_timestamps = collections.deque([now - 2.0, now - 2.0])
    # The method cleans up old timestamps internally, so this should pass
    risk_manager._rate_limit_check()