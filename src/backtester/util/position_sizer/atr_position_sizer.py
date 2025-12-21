import numpy as np
import pandas as pd

import math
from backtester.util.position_sizer.position_sizer import PositionSizer
from backtester.util.util import BarTuple

class ATRPositionSizer(PositionSizer):
    def __init__(self, config: dict, symbol_list: list):
        self.atr_window = config["atr_window"]
        self.atr_multiplier = config["atr_multiplier"]
        self.symbol_list = symbol_list

        self.historical_atr = {sym: [] for sym in self.symbol_list}

    def get_position_size(self, risk_per_trade: float, total_holdings: float, rounding: int, ticker: str):
        """
        Note there is a flaw in the rounding to nearest decimal place which is inherent in floating point arithmetic
        TODO: move to the decimal library
        """
        atr_list = self.historical_atr[ticker]
        if len(atr_list) > 0:  # check for ATR > 0 to prevent ZeroDivisionError, else, reuse previous position size
            atr = self.historical_atr[ticker][-1]
            if atr:
                capital_to_risk = risk_per_trade * total_holdings
                print("atr: ", atr, " capital_to_risk: ", capital_to_risk)
                position_size = capital_to_risk / (atr * self.atr_multiplier) # btc can come in fractional amts, hence cannot use integer division
                 # round to the nearest integer
                if rounding == 0:
                    return math.floor(position_size)
                # round to the nearest decimal place
                multiplier = 10 ** rounding
                position_size *= multiplier
                position_size = int(position_size)
                position_size /= multiplier
                return position_size
        return None


    def on_interval(self, histories: dict[str, list[BarTuple]]):
        for (ticker, interval), history in histories.items():
            atr = self._calc_atr(ticker, history)
            if atr:
                self.historical_atr[ticker].append(atr)


    def _calc_atr(self, ticker: str, history: list[BarTuple]):  # # Use Wilder's Smoothing
        if len(self.historical_atr[ticker]) < 1:  # initialization of average true range uses simple arithmetic mean
            bar_data = history[-self.atr_window - 1:]
            if len(bar_data) < self.atr_window + 1:
                return

            bar_data = pd.DataFrame(bar_data)
            bar_data["h-l"] = bar_data["high"] - bar_data["low"]
            bar_data["h-prev"] = abs(bar_data["high"] - bar_data["close"].shift(periods=1))
            bar_data["l-prev"] = abs(bar_data["low"] - bar_data["close"].shift(periods=1))

            tr = np.nanmax(bar_data[["h-l", "h-prev", "l-prev"]], axis=1)

            atr = np.nanmean(tr)
        else:
            prev_bar_data = history[-2]
            current_bar_data = history[-1]

            high_minus_low = current_bar_data.high - current_bar_data.low
            high_minus_prev = abs(current_bar_data.high - prev_bar_data.close)
            low_minus_prev = abs(current_bar_data.low - prev_bar_data.close)

            tr = max(high_minus_low, high_minus_prev, low_minus_prev)
            atr = 1 / self.atr_window * tr + (1 - 1 / self.atr_window) * self.historical_atr[ticker][-1]

        return atr
