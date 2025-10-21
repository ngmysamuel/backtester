from backtester.util.slippage.slippage import Slippage

class NoSlippage(Slippage):
  def generate_features(self):
    pass
  def calculate_slippage(self, trade_date, trade_size):
    return 0