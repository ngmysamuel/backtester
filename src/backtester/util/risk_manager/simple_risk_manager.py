from backtester.util.risk_manager.risk_manager import RiskManager


class SimpleRiskManager(RiskManager):
    def __init__(self, data_handler, config: dict(str, float)):
        self.data_handler = data_handler
        self.MAX_ORDER_QTY = config["max_order_quantity"]
        self.MAX_NOTIONAL_VAL = config["max_notional_value"]
        self.MAX_DAILY_LOSS = config["max_notional_value"]
        self.RATE_LIMIT = config["rate_limit"]
        self.PARTICIPATION_LIMIT = config["participation_limit"]
        self.INTERVAL = config["interval"]

    def is_allowed(self, ticker: str, quantity: int) -> bool:
        if quantity > self.MAX_ORDER_QTY:
            return False
        latest_bar = self.data_handler.get_latest_bars(ticker)[0]
