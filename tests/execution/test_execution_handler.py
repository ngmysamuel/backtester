import pandas as pd
from backtester.execution.execution_handler import ExecutionHandler
from types import SimpleNamespace
from backtester.events.fill_event import FillEvent

class MockDatHandler:
  def get_latest_bars(self, ticker):
    bar = SimpleNamespace(
      Index=pd.to_datetime("2023-01-01 10:00:00"),
      open=100,
      close=110,
      ticker="MSFT",
    )
    return [bar]


def test_on_market():
  """
  Test that on_market processes orders correctly.
  """
  exec = ExecutionHandler([], MockDatHandler(), "16:00", "1d")
  exec.on_order(
    SimpleNamespace(
      ticker="MSFT",
      order_type=SimpleNamespace(name="MOC"),
      direction=SimpleNamespace(value=1),
      quantity=10,
      timestamp=1672567100,
  )
  )
  exec.on_market(None)
  assert len(exec.events) == 1
  fill = exec.events[0]
  assert isinstance(fill, FillEvent)
  assert fill.ticker == "MSFT"
  assert fill.fill_cost == 1100  # 10 * 110
  assert fill.quantity == 10
