from collections import deque
from types import SimpleNamespace
import pytest
import pandas as pd

from backtester.execution.simulated_execution_handler import SimulatedExecutionHandler
from backtester.events.fill_event import FillEvent
from backtester.enums.order_type import OrderType
from backtester.enums.direction_type import DirectionType

# --- Mocks and Fixtures ---

class MockDataHandler:
    def __init__(self, bars_map):
        self._bars = bars_map

    def get_latest_bars(self, ticker, n=1):
        return self._bars.get(ticker, [])

class MockSlippageModel:
    def __init__(self, slippage=0.0):
        self.slippage = slippage
    def calculate_slippage(self, ticker, timestamp, quantity):
        return self.slippage

@pytest.fixture
def mock_data_handler():
    """Provides a data handler with mock bar data."""
    bars = {
        "MSFT": [SimpleNamespace(Index=pd.to_datetime("2023-01-02 10:00:00"), open=100, close=105)],
        "AAPL": [SimpleNamespace(Index=pd.to_datetime("2023-01-02 10:00:00"), open=150, close=155)],
    }
    return MockDataHandler(bars)

@pytest.fixture
def mock_slippage_model():
    """Provides a mock slippage model that returns zero slippage."""
    return MockSlippageModel()

@pytest.fixture
def execution_handler(mock_data_handler, mock_slippage_model):
    """Returns a SimulatedExecutionHandler instance."""
    return SimulatedExecutionHandler(deque(), mock_data_handler, mock_slippage_model)

def create_mock_order(ticker, order_type, timestamp_str, direction=DirectionType.BUY):
    """Helper to create a mock order event."""
    return SimpleNamespace(
        ticker=ticker,
        order_type=order_type,
        direction=direction,
        quantity=10,
        timestamp=pd.to_datetime(timestamp_str).timestamp()
    )

# --- Test Cases ---

def test_on_order_adds_to_queue(execution_handler):
    """Verify that on_order correctly adds an order to the internal queue."""
    order = create_mock_order("MSFT", OrderType.MKT, "2023-01-01")
    execution_handler.on_order(order)
    assert len(execution_handler.order_queue) == 1
    assert execution_handler.order_queue[0] == order

def test_on_market_fills_mkt_order(execution_handler):
    """Ensure a standard market order is filled immediately on the next market event."""
    order = create_mock_order("MSFT", OrderType.MKT, "2023-01-01")
    execution_handler.on_order(order)
    assert len(execution_handler.order_queue) == 1

    execution_handler.on_market(None, mkt_close=False)
    
    assert len(execution_handler.events) == 1
    fill = execution_handler.events[0]
    assert isinstance(fill, FillEvent)
    assert fill.ticker == "MSFT"
    assert fill.fill_cost == 1000  # 10 * 100 (open price) with 0 slippage
    assert len(execution_handler.order_queue) == 0

def test_on_market_fills_moc_order_at_close(execution_handler):
    """Verify a MOC order is filled correctly when the market is closing."""
    order = create_mock_order("MSFT", OrderType.MOC, "2023-01-01")
    execution_handler.on_order(order)

    execution_handler.on_market(None, mkt_close=True)

    assert len(execution_handler.events) == 1
    fill = execution_handler.events[0]
    assert fill.fill_cost == 1050  # 10 * 105 (close price)
    assert len(execution_handler.order_queue) == 0

def test_on_market_defers_moc_order_before_close(execution_handler):
    """Ensure a MOC order is not filled if the market is not closing."""
    order = create_mock_order("MSFT", OrderType.MOC, "2023-01-01")
    execution_handler.on_order(order)

    execution_handler.on_market(None, mkt_close=False)

    assert len(execution_handler.events) == 0
    assert len(execution_handler.order_queue) == 1

def test_on_market_defers_future_order(execution_handler):
    """Check that an order is not filled if its timestamp is later than the current market data's time."""
    # Bar data is at 2023-01-02 10:00:00
    order = create_mock_order("MSFT", OrderType.MKT, "2023-01-03") # Order from the future
    execution_handler.on_order(order)

    execution_handler.on_market(None, mkt_close=False)

    assert len(execution_handler.events) == 0
    assert len(execution_handler.order_queue) == 1

def test_on_market_processes_mixed_orders(execution_handler):
    """Test the handler's ability to process a queue with both MKT and MOC orders."""
    mkt_order = create_mock_order("MSFT", OrderType.MKT, "2023-01-01")
    moc_order = create_mock_order("AAPL", OrderType.MOC, "2023-01-01")
    execution_handler.on_order(mkt_order)
    execution_handler.on_order(moc_order)

    # First, run before market close
    execution_handler.on_market(None, mkt_close=False)
    
    assert len(execution_handler.events) == 1  # Only MKT order filled
    assert execution_handler.events[0].ticker == "MSFT"
    assert len(execution_handler.order_queue) == 1 # MOC order remains
    
    # Now, run at market close
    execution_handler.on_market(None, mkt_close=True)

    assert len(execution_handler.events) == 2 # MOC order is now filled
    assert execution_handler.events[1].ticker == "AAPL"
    assert len(execution_handler.order_queue) == 0

def test_on_market_handles_no_bar_data(execution_handler):
    """The current code should raise an IndexError if no bar data is available. This test confirms that."""
    order = create_mock_order("GOOG", OrderType.MKT, "2023-01-01") # GOOG has no data in mock
    execution_handler.on_order(order)

    with pytest.raises(IndexError):
        execution_handler.on_market(None, mkt_close=False)

def test_on_market_with_empty_queue(execution_handler):
    """Ensure the handler doesn't crash if on_market is called when no orders are pending."""
    try:
        execution_handler.on_market(None, mkt_close=False)
    except Exception as e:
        pytest.fail(f"on_market with empty queue raised an exception: {e}")
    assert len(execution_handler.events) == 0

def test_on_market_fills_mkt_order_with_slippage_buy(mock_data_handler):
    """Test that slippage is correctly applied for a BUY MKT order."""
    mock_slippage_model = MockSlippageModel(slippage=0.01) # 1% slippage
    execution_handler = SimulatedExecutionHandler(deque(), mock_data_handler, mock_slippage_model)
    
    order = create_mock_order("MSFT", OrderType.MKT, "2023-01-01", direction=DirectionType.BUY)
    execution_handler.on_order(order)
    execution_handler.on_market(None, mkt_close=False)

    assert len(execution_handler.events) == 1
    fill = execution_handler.events[0]
    assert fill.fill_cost == 1010 # 10 * 100 * (1 + 0.01)

def test_on_market_fills_mkt_order_with_slippage_sell(mock_data_handler):
    """Test that slippage is correctly applied for a SELL MKT order."""
    mock_slippage_model = MockSlippageModel(slippage=0.01) # 1% slippage
    execution_handler = SimulatedExecutionHandler(deque(), mock_data_handler, mock_slippage_model)
    
    order = create_mock_order("MSFT", OrderType.MKT, "2023-01-01", direction=DirectionType.SELL)
    execution_handler.on_order(order)
    execution_handler.on_market(None, mkt_close=False)

    assert len(execution_handler.events) == 1
    fill = execution_handler.events[0]
    assert fill.fill_cost == 990 # 10 * 100 * (1 - 0.01)

def test_on_market_processes_multiple_mkt_orders(execution_handler):
    """Test that multiple MKT orders are processed in one go."""
    order1 = create_mock_order("MSFT", OrderType.MKT, "2023-01-01")
    order2 = create_mock_order("AAPL", OrderType.MKT, "2023-01-01")
    execution_handler.on_order(order1)
    execution_handler.on_order(order2)

    execution_handler.on_market(None, mkt_close=False)

    assert len(execution_handler.events) == 2
    assert execution_handler.events[0].ticker == "MSFT"
    assert execution_handler.events[1].ticker == "AAPL"
    assert len(execution_handler.order_queue) == 0
