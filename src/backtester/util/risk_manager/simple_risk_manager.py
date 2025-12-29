from backtester.util.risk_manager.risk_manager import RiskManager
from backtester.events.order_event import OrderEvent
from backtester.enums.direction_type import DirectionType
from backtester.util.util import BarTuple
import collections
import time
class SimpleRiskManager(RiskManager):
    def __init__(self, config: dict[str, float]):
        self.MAX_ORDER_QTY = config["max_order_quantity"]
        self.MAX_NOTIONAL_VAL = config["max_notional_value"]
        self.MAX_DAILY_LOSS = config["max_daily_loss"]
        self.MAX_EXPOSURE = config["max_exposure"]
        self.PARTICIPATION_WINDOW = config["participation_window"]
        self.PARTICIPATION_LIMIT = config["participation_limit"]
        self.RATE_LIMIT = config["rate_limit"]
        self.RATE_INTERVAL = 1 # 1 second

        self.order_timestamps = collections.deque([])

    def is_allowed(self, order: OrderEvent, daily_open_value: dict[str, float], history: list[BarTuple], symbol_list: list[str], holdings: dict) -> bool:
        if not history:
            return False

        estimated_current_price = history[-1].close

        if self.MAX_ORDER_QTY != -1 and order.quantity > self.MAX_ORDER_QTY:
            print(f"Max Order Quantity check failed - {order.quantity} > {self.MAX_ORDER_QTY}")
            return False

        if self.MAX_NOTIONAL_VAL != -1 and order.quantity * estimated_current_price > self.MAX_NOTIONAL_VAL:
            print(f"Max Notional Value check failed - {order.quantity * estimated_current_price} > {self.MAX_NOTIONAL_VAL}")
            return False

        open_value = daily_open_value.get(order.strategy_name,0.0)
        if open_value != 0:
            pnl = (holdings["total"] - open_value) / open_value
            if pnl < -self.MAX_DAILY_LOSS and order.direction == DirectionType.BUY:
                print(f"Daily loss limit failed - {pnl} < {-self.MAX_DAILY_LOSS} and is BUY order")
                return False

        exposure = sum([abs(holdings[ticker]["value"]) for ticker in symbol_list])
        estimated_future_exposure = exposure + order.quantity * estimated_current_price
        if self.MAX_EXPOSURE != -1 and estimated_future_exposure > self.MAX_EXPOSURE:
            print(f"Exposure check failed - {estimated_future_exposure} > {self.MAX_EXPOSURE}")
            return False

        if len(history) >= self.PARTICIPATION_WINDOW:
            total_volume = sum([bar.volume for bar in history[-self.PARTICIPATION_WINDOW:]])
            avg_volume = total_volume / self.PARTICIPATION_WINDOW
            if avg_volume != 0:
                participation_rate = order.quantity / avg_volume
                if participation_rate > self.PARTICIPATION_LIMIT:
                    print(f"participation check failed - {participation_rate} > {self.PARTICIPATION_LIMIT}")
                    return False
            else:
                print(f"participation check failed - zero volume over the pass {self.PARTICIPATION_WINDOW} periods")
                return False

        last_time_step = time.time() - self.RATE_INTERVAL
        while self.order_timestamps:
            if self.order_timestamps[0] < last_time_step:
                self.order_timestamps.popleft()
            else:
                break
        if len(self.order_timestamps) > self.RATE_LIMIT:
            print(f"Rate limit check failed - {len(self.order_timestamps)} > {self.RATE_LIMIT}")
            return False

        self.order_timestamps.append(order.timestamp)
        return True
