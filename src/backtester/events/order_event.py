from abc import ABC

from backtester.enums.direction_type import DirectionType
from backtester.enums.order_type import OrderType


class OrderEvent(ABC):
  def __init__(self, direction: DirectionType, ticker: str, order_type: OrderType, quantity: int, timestamp: float):
    self.type = "ORDER"
    self.direction = direction
    self.ticker = ticker
    self.order_type = order_type
    self.quantity = quantity
    self.timestamp = timestamp