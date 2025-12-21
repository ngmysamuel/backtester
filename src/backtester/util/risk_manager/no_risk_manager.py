from backtester.util.risk_manager.risk_manager import RiskManager


class NoRiskManager(RiskManager):
    def is_allowed(self) -> bool:
        return True
