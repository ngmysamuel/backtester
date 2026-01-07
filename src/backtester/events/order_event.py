from abc import ABC
import uuid
from backtester.enums.direction_type import DirectionType
from backtester.enums.order_type import OrderType


class OrderEvent(ABC):
    def __init__(self, direction: DirectionType, ticker: str, strategy_name: str, order_type: OrderType, quantity: int, timestamp: float):
        self.id = uuid.uuid4()
        self.type = "ORDER"
        self.direction = direction
        self.ticker = ticker
        self.strategy_name = strategy_name
        self.order_type = order_type
        self.quantity = quantity
        self.timestamp = timestamp
