from backtester.util.slippage.slippage import Slippage


class NoSlippage(Slippage):
    def __init__(self, *args, **kwargs):
        super().__init__()

    def calculate_slippage(self, *args, **kwargs):
        return 0

    def on_interval(self, *args, **kwargs):
        pass
