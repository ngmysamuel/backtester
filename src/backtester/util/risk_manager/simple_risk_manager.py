from backtester.util.risk_manager.risk_manager import RiskManager
from backtester.events.order_event import OrderEvent
import numpy as np
from backtester.util.util import BarTuple
import collections
import time
class SimpleRiskManager(RiskManager):
    def __init__(self, config: dict[str, float]):
        self.MAX_ORDER_QTY = config["max_order_quantity"]
        self.MAX_NOTIONAL_VAL = config["max_notional_value"]
        self.MAX_DAILY_LOSS = config["max_daily_loss"]
        self.MAX_GROSS_EXPOSURE = config["max_gross_exposure"]
        self.MAX_NET_EXPOSURE = config["max_net_exposure"]
        self.PARTICIPATION_WINDOW = config["participation_window"]
        self.PARTICIPATION_LIMIT = config["participation_limit"]
        self.RATE_LIMIT = config["rate_limit"]
        self.RATE_INTERVAL = 1 # 1 second

        self.order_timestamps = collections.deque([])

    def is_allowed(self, order: OrderEvent, daily_open_value: dict[str, float], history: list[BarTuple], symbol_list: list[str], holdings: dict) -> bool:
        if not history:
            return False

        estimated_current_price = history[-1].close
        open_value = daily_open_value.get(order.strategy_name,0.0)

        try:
            self._max_order_quantity_check(order)
            self._max_notional_value_check(order, estimated_current_price)
            self._daily_loss_limit_check(order, holdings, open_value)
            self._gross_exposure_check(order, symbol_list, holdings, estimated_current_price)
            self._net_exposure_check(order, symbol_list, holdings, estimated_current_price)
            self._participation_check(order, history)
            self._rate_limit_check()
        except ValueError as e:
            print(e)
            return False

        self.order_timestamps.append(order.timestamp)
        return True

    def _max_order_quantity_check(self, order: OrderEvent) -> None:
        if self.MAX_ORDER_QTY != -1 and order.quantity > self.MAX_ORDER_QTY:
            raise ValueError(f"Max Order Quantity check failed - {order.quantity} > {self.MAX_ORDER_QTY}")
            
    def _max_notional_value_check(self, order: OrderEvent, estimated_current_price: float) -> None:
        if self.MAX_NOTIONAL_VAL != -1 and order.quantity * estimated_current_price > self.MAX_NOTIONAL_VAL:
            raise ValueError(f"Max Notional Value check failed - {order.quantity * estimated_current_price} > {self.MAX_NOTIONAL_VAL}")

    def _daily_loss_limit_check(self, order: OrderEvent, holdings: dict, open_value: float) -> None:
        if open_value != 0:
            pnl = (holdings["total"] - open_value) / open_value
            order_signed_quantity = order.direction.value * order.quantity
            net_direction = np.sign(order_signed_quantity) * np.sign(holdings[order.ticker]["position"])
            if pnl < -self.MAX_DAILY_LOSS and net_direction > 0:
                raise ValueError(f"Daily loss limit failed - {pnl} < {-self.MAX_DAILY_LOSS} and position remains OPEN")

    def _gross_exposure_check(self, order: OrderEvent, symbol_list: list[str], holdings: dict, estimated_current_price: float) -> None:
        gross_exposure = 0
        for ticker in symbol_list:
            if ticker == order.ticker: # get the new position's value
                gross_exposure += abs(holdings[ticker].get("value", 0) + order.quantity * estimated_current_price * order.direction.value)
            else:
                gross_exposure += abs(holdings[ticker].get("value", 0))
        if self.MAX_GROSS_EXPOSURE != -1 and gross_exposure > self.MAX_GROSS_EXPOSURE:
            raise ValueError(f"Gross Exposure check failed - {gross_exposure} > {self.MAX_GROSS_EXPOSURE}")

    def _net_exposure_check(self, order: OrderEvent, symbol_list: list[str], holdings: dict, estimated_current_price: float) -> None:
        net_exposure = sum([holdings[ticker]["value"] for ticker in symbol_list])
        estimated_net_future_exposure = net_exposure + order.quantity * estimated_current_price * order.direction.value
        if self.MAX_NET_EXPOSURE != -1 and abs(estimated_net_future_exposure) > self.MAX_NET_EXPOSURE:
            raise ValueError(f"Net Exposure check failed - {estimated_net_future_exposure} > {self.MAX_NET_EXPOSURE}")

    def _participation_check(self, order: OrderEvent, history: list[BarTuple]):
        if len(history) >= self.PARTICIPATION_WINDOW:
            total_volume = sum([bar.volume for bar in history[-self.PARTICIPATION_WINDOW:]])
            avg_volume = total_volume / self.PARTICIPATION_WINDOW
            if avg_volume != 0:
                participation_rate = order.quantity / avg_volume
                if participation_rate > self.PARTICIPATION_LIMIT:
                    raise ValueError(f"participation check failed - {participation_rate} > {self.PARTICIPATION_LIMIT}")
                    return False
            else:
                raise ValueError(f"participation check failed - zero volume over the past {self.PARTICIPATION_WINDOW} periods")
                return False

    def _rate_limit_check(self):
        last_time_step = time.time() - self.RATE_INTERVAL
        while self.order_timestamps:
            if self.order_timestamps[0] < last_time_step:
                self.order_timestamps.popleft()
            else:
                break
        if len(self.order_timestamps) > self.RATE_LIMIT:
            raise ValueError(f"Rate limit check failed - {len(self.order_timestamps)} > {self.RATE_LIMIT}")