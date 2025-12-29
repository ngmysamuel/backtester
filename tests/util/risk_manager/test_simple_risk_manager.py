import time

import pytest

from backtester.enums.direction_type import DirectionType
from backtester.enums.order_type import OrderType
from backtester.events.order_event import OrderEvent
from backtester.util.risk_manager.simple_risk_manager import SimpleRiskManager
from backtester.util.util import BarTuple


@pytest.fixture
def default_config():
    return {
        "max_order_quantity": 100,
        "max_notional_value": 10000,
        "max_daily_loss": 0.05,
        "max_exposure": 50000,
        "participation_window": 5,
        "participation_limit": 0.1,
        "rate_limit": 5
    }

@pytest.fixture
def risk_manager(default_config):
    return SimpleRiskManager(default_config)

@pytest.fixture
def history():
    # 5 bars, price 100, volume 1000
    return [BarTuple(time.time(), 100, 100, 100, 100, 1000, None) for _ in range(5)]

@pytest.fixture
def holdings():
    return {
        "total": 100000,
        "AAPL": {"value": 45000}, # 45k exposure
        "MSFT": {"value": 0}
    }

# class TestRiskManagerLogic:

def test_zero_division_fix(risk_manager, history, holdings):
    """
    Verifies that the code handles 0.0 starting capital/open_value 
    without crashing (ZeroDivisionError).
    """
    daily_open = {"TestStrat": 0.0}
    order = OrderEvent(DirectionType.BUY, "AAPL", "TestStrat", OrderType.MKT, 10, time.time())
    
    # Should return True (allowed) or False, but NOT raise Exception
    try:
        allowed = risk_manager.is_allowed(order, daily_open, history, ["AAPL", "MSFT"], holdings)
        assert allowed is True # Assuming we default to allow if we can't calc PnL
    except ZeroDivisionError:
        pytest.fail("Risk Manager raised ZeroDivisionError on 0.0 open value")

def test_future_exposure_logic(risk_manager, history, holdings):
    """
    The manager should reject an order if Current Exposure + New Order > Max Exposure.
    """
    # Config Max Exposure: 50,000
    # Current Holdings: 45,000
    # Order: 60 shares @ 100 = 6,000
    # Projected: 51,000 (Should Fail)
    
    daily_open = {"TestStrat": 100000.0}
    order = OrderEvent(DirectionType.BUY, "AAPL", "TestStrat", OrderType.MKT, 60, time.time())
    
    allowed = risk_manager.is_allowed(order, daily_open, history, ["AAPL", "MSFT"], holdings)
    
    assert allowed is False, "Manager failed to block trade that would exceed FUTURE exposure limits"

def test_zero_volume_behavior(risk_manager, holdings):
    """
    Reject on 0 volume.
    """
    # Create history with 0 volume
    zero_vol_history = [BarTuple(time.time(), 100, 100, 100, 100, 0, None) for _ in range(5)]
    
    daily_open = {"TestStrat": 100000.0}
    order = OrderEvent(DirectionType.BUY, "AAPL", "TestStrat", OrderType.MKT, 10, time.time())
    
    allowed = risk_manager.is_allowed(order, daily_open, zero_vol_history, ["AAPL"], holdings)
    
    assert allowed is False, "Zero volume securities cannot be traded"

def test_standard_participation(risk_manager, history, holdings):
    """Standard check: Order > 10% of Avg Volume (1000) -> >100 shares"""
    daily_open = {"TestStrat": 100000.0}
    
    # 101 shares > 100 (10% of 1000)
    # Note: Max order qty is 100 in config, so we must set order < max_qty to test participation
    # Let's lower participation limit in this specific test or increase max_qty
    
    risk_manager.MAX_ORDER_QTY = 500 # Increase hard cap
    
    order = OrderEvent(DirectionType.BUY, "AAPL", "TestStrat", OrderType.MKT, 101, time.time())
    allowed = risk_manager.is_allowed(order, daily_open, history, ["AAPL"], holdings)
    
    assert allowed is False, "Should block orders exceeding participation limit"