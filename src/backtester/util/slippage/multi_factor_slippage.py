import bidask
import numpy as np

from backtester.util.slippage.slippage import Slippage


class MultiFactorSlippage(Slippage):

  def __init__(self, df_dict, config):
    self.feature_df_dict = {}
    for key, val in df_dict.items():
      self.feature_df_dict[key] = val.copy()
    self.PERIODS_IN_YEAR = config["periods_in_year"]
    self.short_window = config["short_window"]
    self.med_window = config["med_window"]
    self.long_window = config["long_window"]
    self.power_law_exponent = config["power_law_exponent"]
    self.upper_lim_vol_surge = config["upper_lim_vol_surge"]
    self.bidask_window = config["bidask_window"]
    self.volatility_cost_factor = config["volatility_cost_factor"]
    self.market_impact_factor = config["market_impact_factor"]
    self.momentum_cost_factor = config["momentum_cost_factor"]
    self.liquidity_cost_factor = config["liquidity_cost_factor"]
    self.liquidity_cost_exponent = config["liquidity_cost_exponent"]
    self.random_noise = config["random_noise"]


  def generate_features(self):
    self._calculate_volatility_metrics()
    self._calculate_volume_metrics()
    self._calculate_composite_metrics()


  def _calculate_volatility_metrics(self):
    for feature_df in self.feature_df_dict.values():
      # Basic price metrics
      feature_df["returns"] = feature_df["close"].pct_change()

      # Volatility with different timeframes
      feature_df["vol_short"] = feature_df["returns"].rolling(self.short_window).std() * np.sqrt(self.PERIODS_IN_YEAR)
      feature_df["vol_med"] = feature_df["returns"].rolling(self.med_window).std() * np.sqrt(self.PERIODS_IN_YEAR)
      feature_df["vol_long"] = feature_df["returns"].rolling(self.long_window).std() * np.sqrt(self.PERIODS_IN_YEAR)

      price_cols = [
        "returns", "vol_short", "vol_med", "vol_long"
      ]
      feature_df[price_cols] = feature_df[price_cols].fillna(method="ffill").fillna(0)


  def _calculate_volume_metrics(self):
    for feature_df in self.feature_df_dict.values():
      # volume moving averages with different timeframes
      feature_df["vol_ma_short"] = feature_df["volume"].rolling(self.short_window).mean()
      feature_df["vol_ma_med"] = feature_df["volume"].rolling(self.med_window).mean()
      feature_df["vol_ma_long"] = feature_df["volume"].rolling(self.long_window).mean()

      # Volume ratios
      feature_df["vol_ratio_short"] = feature_df["volume"] / feature_df["vol_ma_short"]
      feature_df["vol_ratio_med"] = feature_df["volume"] / feature_df["vol_ma_med"]
      feature_df["vol_ratio_long"] = feature_df["volume"] / feature_df["vol_ma_long"]

      # Non-linear volume metrics
      #   Indicator if today's volume is an outlier - capped to a max to prevent extreme events from 
      #   diproportionately affecting the model
      #   Use long term average of the volume for outlier identification
      feature_df["vol_surge"] = np.clip(feature_df["vol_ratio_long"], None, self.upper_lim_vol_surge)

      volume_cols = [
        "vol_ma_short", "vol_ma_med", "vol_ma_long", "vol_surge"
      ]
      feature_df[volume_cols] = feature_df[volume_cols].fillna(method="ffill").fillna(1)


  def _calculate_composite_metrics(self):
    for feature_df in self.feature_df_dict.values():

      # Price movement per dollar traded - a high value means very illiquid
      #   https://breakingdownfinance.com/finance-topics/alternative-investments/amihud-illiquidity-measure/
      #   https://www.cis.upenn.edu/~mkearns/finread/amihud.pdf
      feature_df["amihud_illiq"] = abs(feature_df["returns"]) / (feature_df["volume"] * feature_df["close"])

      # Total dollar value in a trading interval
      feature_df["turnover"] = feature_df["volume"] * feature_df["close"]

      # Calculates the Coeff of Variation by dividing the standard deviation with the mean giving a standardised
      # measure of volatility that can be used across shares of different capitalization
      feature_df["turnover_vol"] = (
        feature_df["turnover"].rolling(self.med_window).std() / feature_df["turnover"].rolling(self.med_window).mean()
      )

      # indicates the direction of market this stock is moving in
      feature_df["price_acceleration"] = feature_df["returns"].diff()

      # Bid-ask spread estimation - https://github.com/eguidotti/bidask
      feature_df["spread_cost"] = bidask.edge_rolling(feature_df[["open","high","low","close"]], self.bidask_window) / 2

      # models the cost of a chaotic market
      feature_df["volatility_cost"] = (
        feature_df["vol_med"] * np.exp(feature_df["vol_surge"] - 1) * self.volatility_cost_factor
      )

      # models the cost of chasing a moving target
      feature_df["momentum_cost"] = (
        self.momentum_cost_factor * abs(feature_df["returns"]) * np.sign(feature_df["price_acceleration"])
      )

      # models the cost of trading in a blue chip MSFT vs a penny stock no one knows
      feature_df["liquidity_cost"] = (
        self.liquidity_cost_factor * np.power(np.clip(feature_df["amihud_illiq"], 1e-8, None), self.liquidity_cost_exponent)
      )

      impact_cols = [
        "amihud_illiq",
        "turnover",
        "turnover_vol",
        "price_acceleration",
        "spread_cost",
        "volatility_cost",
        "momentum_cost",
        "liquidity_cost"
      ]
      feature_df[impact_cols] = feature_df[impact_cols].fillna(method="ffill").fillna(0)


  def calculate_slippage(self, ticker, trade_date, trade_size):
    """
    Slippage = (Spread Cost) + (Amplified Market Impact) + (Momentum Cost*Liquidity Cost) + (Random Noise)
    The default values in cofig.yaml supports daily data. You must update it if using any other period data.
    """

    characteristics = self.feature_df_dict[ticker].loc[trade_date]

    # 1. Calculate the participation rate for this trade
    participation_rate = 0 # Handle no-volume days
    if characteristics["volume"] > 0:
        participation_rate = trade_size / characteristics["volume"]

    # 2. Using (1) to calculate market impact with decay
    market_impact = (
      self.market_impact_factor
      * np.power(participation_rate / np.clip(characteristics["vol_ratio_med"], 1e-8, None), self.power_law_exponent)
      * characteristics["vol_med"]
      * np.exp(-characteristics["turnover_vol"])
    )

    # 3. Random market noise (increased variance)
    noise = np.random.normal(0, self.random_noise)

    # 4. Combine components with non-linear interactions
    slippage = (
      characteristics["spread_cost"]
      + market_impact * (1 + characteristics["volatility_cost"])
      + characteristics["momentum_cost"] * characteristics["liquidity_cost"]
      + noise
    ).clip(
      0, 0.05
    )  # Cap at 5%

    return slippage
