import bidask
import numpy as np
import pandas as pd

from backtester.util.slippage.slippage import Slippage


class MultiFactorSlippage(Slippage):
    def __init__(self, symbol_list, data_handler, config, mode="backtest"):
        """
        :param df_dict: Dictionary of historical DataFrames (required for backtest, optional for live warm-up)
        :param config: Configuration dictionary
        :param mode: 'backtest' or 'live'
        """
        self.symbol_list = symbol_list
        self.data_handler = data_handler
        self.df_dict = data_handler.symbol_raw_data
        self.config = config
        self.mode = mode

        # Unpack config vars
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

        # Determine the maximum lookback needed for calculation
        self.max_lookback = max(self.long_window, self.med_window, self.short_window, self.bidask_window) + 5  # Add buffer for diff/pct_change calculations

        # State containers
        self.feature_df_dict = {}  # For Backtest (Pre-computed)
        self.live_buffers = {}  # For Live (Rolling window)

        # Initialization logic
        if self.mode == "live":
            self._init_live_mode(self.df_dict)
        else:
            self._init_backtest_mode(self.df_dict)

    def _init_backtest_mode(self, df_dict):
        """Pre-computes features on the entire history for speed."""
        for ticker, df in df_dict.items():
            # We work on a copy to avoid side effects
            processed_df = self._compute_features_on_df(df.copy()) # compute all the ratios now
            self.feature_df_dict[ticker] = processed_df

    def _init_live_mode(self, df_dict):
        """Initializes buffers, optionally warming up with history."""
        if df_dict:
            for ticker, df in df_dict.items():
                # Keep only the tail needed for calculation
                if df:
                    self.live_buffers[ticker] = df[-self.max_lookback :].copy() # update our df, computation happens on demand

    def on_market(self):
        """
        This method is called when new OHLCV data arrives.
        new_bar: A namedtuple containing Index (timestamp), open, high, low, close
        """
        if self.mode != "live":
            return
        for ticker in self.symbol_list:
            if not self.data_handler.get_latest_bars(ticker):
                continue
            new_row = self.data_handler.get_latest_bars(ticker)[0]
            new_df = pd.DataFrame([new_row])
            new_df.set_index("Index", inplace=True)
            if ticker not in self.live_buffers:
                self.live_buffers[ticker] = new_df
            else:
                # Append new row
                self.live_buffers[ticker] = pd.concat([self.live_buffers[ticker], new_df])

                # Prune buffer to keep memory usage constant
                if len(self.live_buffers[ticker]) > self.max_lookback:
                    self.live_buffers[ticker] = self.live_buffers[ticker].iloc[-self.max_lookback :]

    def _compute_features_on_df(self, df):
        """
        Pure logic method. Applies math columns to ANY DataFrame
        (whether it's 10 years of history or a 50-day live buffer).
        """
        if len(df) < 2:
            return df

        # Basic price metrics
        df["returns"] = df["close"].pct_change()

        # Helper for filling NaNs specific to this method scope
        def clean_col(cols, fill_val=0):
            df[cols] = df[cols].ffill().fillna(fill_val)

        ##################
        # Volatility Metrics
        ##################

        # Volatility with different timeframes
        df["vol_short"] = df["returns"].rolling(self.short_window).std() * np.sqrt(self.PERIODS_IN_YEAR)
        df["vol_med"] = df["returns"].rolling(self.med_window).std() * np.sqrt(self.PERIODS_IN_YEAR)
        df["vol_long"] = df["returns"].rolling(self.long_window).std() * np.sqrt(self.PERIODS_IN_YEAR)

        clean_col(["returns", "vol_short", "vol_med", "vol_long"], 0)

        ##################
        # Volume Metrics
        ##################

        # Volume moving averages with different timeframes
        df["vol_ma_short"] = df["volume"].rolling(self.short_window).mean()
        df["vol_ma_med"] = df["volume"].rolling(self.med_window).mean()
        df["vol_ma_long"] = df["volume"].rolling(self.long_window).mean()

        # Volume ratios
        # Handle division by zero if volume MA is 0
        df["vol_ratio_short"] = df["volume"] / df["vol_ma_short"].replace(0, np.nan)
        df["vol_ratio_med"] = df["volume"] / df["vol_ma_med"].replace(0, np.nan)
        df["vol_ratio_long"] = df["volume"] / df["vol_ma_long"].replace(0, np.nan)
        
        # Non-linear volume metrics
        #   Indicator if today's volume is an outlier - capped to a max to prevent extreme events from 
        #   diproportionately affecting the model
        #   Use long term average of the volume for outlier identification
        df["vol_surge"] = np.clip(df["vol_ratio_long"], None, self.upper_lim_vol_surge)

        clean_col(["vol_ma_short", "vol_ma_med", "vol_ma_long", "vol_surge"], 1)

        ##################
        # Composite Metrics
        ##################

        # Amihud - Price movement per dollar traded - a high value means very illiquid
        #   https://breakingdownfinance.com/finance-topics/alternative-investments/amihud-illiquidity-measure/
        #   https://www.cis.upenn.edu/~mkearns/finread/amihud.pdf
        df["amihud_illiq"] = abs(df["returns"]) / (df["volume"] * df["close"]).replace(0, np.nan)
        
        # Total dollar value in a trading interval
        df["turnover"] = df["volume"] * df["close"]

        # Calculates the Coeff of Variation by dividing the standard deviation with the mean giving a standardised
        # measure of volatility that can be used across shares of different capitalization
        to_roll_std = df["turnover"].rolling(self.med_window).std()
        to_roll_mean = df["turnover"].rolling(self.med_window).mean()
        df["turnover_vol"] = to_roll_std / to_roll_mean

        # indicates the direction of market this stock is moving in
        df["price_acceleration"] = df["returns"].diff()

        # Bid-ask spread estimation - https://github.com/eguidotti/bidask
        # Only run if we have enough data, otherwise 0
        if len(df) >= self.bidask_window:
            df["spread_cost"] = bidask.edge_rolling(df[["open", "high", "low", "close"]], self.bidask_window) / 2
        else:
            df["spread_cost"] = 0

        # models the cost of a chaotic market
        df["volatility_cost"] = df["vol_med"] * np.exp(df["vol_surge"] - 1) * self.volatility_cost_factor

        # models the cost of chasing a moving target
        df["momentum_cost"] = self.momentum_cost_factor * abs(df["returns"]) * np.sign(df["price_acceleration"])

        # models the cost of trading in a blue chip MSFT vs a penny stock no one knows
        df["liquidity_cost"] = self.liquidity_cost_factor * np.power(np.clip(df["amihud_illiq"], 1e-8, None), self.liquidity_cost_exponent)

        impact_cols = ["amihud_illiq", "turnover", "turnover_vol", "price_acceleration", "spread_cost", "volatility_cost", "momentum_cost", "liquidity_cost"]
        clean_col(impact_cols, 0)

        return df

    def calculate_slippage(self, ticker, trade_date, trade_size):
        """
        Calculates slippage.
        If mode is 'backtest', 'trade_date' is required.
        If mode is 'live', 'trade_date' is ignored, uses latest buffer data.
        """

        # Get characteristics based on mode
        if self.mode != "live":
            if trade_date is None:
                raise ValueError("Backtest mode requires trade_date")
            try:
                characteristics = self.feature_df_dict[ticker].loc[trade_date]
            except KeyError:
                # Fallback if date missing
                return 0.0
        else:
            # LIVE MODE
            if ticker not in self.live_buffers or len(self.live_buffers[ticker]) < self.short_window:
                # Not enough data yet to calculate slippage
                return 0.0

            # 1. Update features on the buffer
            # Note: For high-freq, optimize this to not re-calc whole buffer every time.
            # But for standard bars, this is fast enough.
            current_df = self._compute_features_on_df(self.live_buffers[ticker].copy())
            characteristics = current_df.iloc[-1]


        # 1. Participation Rate
        participation_rate = 0
        if characteristics["volume"] > 0:
            participation_rate = trade_size / characteristics["volume"]

        # 2. Market Impact
        # Handle division by zero / nan
        vol_ratio = characteristics["vol_ratio_med"] if characteristics["vol_ratio_med"] > 1e-8 else 1e-8

        market_impact = self.market_impact_factor * np.power(participation_rate / vol_ratio, self.power_law_exponent) * characteristics["vol_med"] * np.exp(-characteristics["turnover_vol"])

        # 3. Noise
        noise = np.random.normal(0, self.random_noise)

        # 4. Final Combination
        slippage = characteristics["spread_cost"] + market_impact * (1 + characteristics["volatility_cost"]) + characteristics["momentum_cost"] * characteristics["liquidity_cost"] + noise

        # Cap at 5%
        return float(np.clip(slippage, 0, 0.05))
