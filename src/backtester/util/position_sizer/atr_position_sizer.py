import numpy as np
import pandas as pd

from backtester.portfolios.portfolio import Portfolio
from backtester.util.position_sizer.position_sizer import PositionSizer


class ATRPositionSizer(PositionSizer):
    def __init__(self, config: dict, symbol_list: list):
        self.atr_window = config["atr_window"]
        self.atr_multiplier = config["atr_multiplier"]
        self.symbol_list = symbol_list

        self.historical_atr = {sym: [] for sym in self.symbol_list}

    def get_position_size(self, portfolio: Portfolio, ticker: str):
        atr_list = self.historical_atr[ticker]
        if len(atr_list) > 0:  # check for ATR > 0 to prevent ZeroDivisionError, else, reuse previous position size
            atr = self.historical_atr[ticker][-1]
            if atr:
                capital_to_risk = min(portfolio.current_holdings["cash"], portfolio.risk_per_trade * portfolio.current_holdings["total"])
                return capital_to_risk // (atr * self.atr_multiplier)
        return None

    def update_historical_atr(self, portfolio: Portfolio, ticker: str):
        atr = self._calc_atr(portfolio, ticker)
        if atr:
            self.historical_atr[ticker].append(atr)

    def _calc_atr(self, portfolio: Portfolio, ticker: str):  # # Use Wilder's Smoothing
        if len(self.historical_atr[ticker]) < 1:  # initialization of average true range uses simple arithmetic mean
            bar_data = portfolio.data_handler.get_latest_bars(ticker, self.atr_window + 1)
            if len(bar_data) < self.atr_window + 1:
                return

            bar_data = pd.DataFrame(bar_data)
            bar_data["h-l"] = bar_data["high"] - bar_data["low"]
            bar_data["h-prev"] = (bar_data["high"] - bar_data["close"].shift(periods=1)).abs()
            bar_data["l-prev"] = (bar_data["low"] - bar_data["close"].shift(periods=1)).abs()

            tr = np.nanmax(bar_data[["h-l", "h-prev", "l-prev"]], axis=1)

            atr = tr.mean()
        else:
            bar_data = portfolio.data_handler.get_latest_bars(ticker, 2)
            bar_data = pd.DataFrame(bar_data)
            bar_data["h-l"] = bar_data["high"] - bar_data["low"]
            bar_data["h-prev"] = (bar_data["high"] - bar_data["close"].shift(periods=1)).abs()
            bar_data["l-prev"] = (bar_data["low"] - bar_data["close"].shift(periods=1)).abs()

            tr = np.nanmax(bar_data[["h-l", "h-prev", "l-prev"]], axis=1)[-1]
            atr = 1 / self.atr_window * tr + (1 - 1 / self.atr_window) * self.historical_atr[ticker][-1]

        return atr
