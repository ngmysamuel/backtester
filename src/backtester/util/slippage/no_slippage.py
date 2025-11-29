from backtester.util.slippage.slippage import Slippage

class NoSlippage(Slippage):
  def __init__(self, *args, **kwargs):
    super().__init__()
  def generate_features(self):
    pass
  def calculate_slippage(self, ticker, trade_date, trade_size):
    return 0