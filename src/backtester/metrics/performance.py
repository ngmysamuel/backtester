import numpy as np
import pandas as pd

def calc_sharpe_ratio(returns, periods=252):
  return np.sqrt(periods) * (np.mean(returns)) / np.std(returns)

def calc_drawdowns(equity_curve):
    """
    Calculate the largest peak-to-trough drawdown of the PnL curve
    as well as the duration of the drawdown. Requires that the 
    pnl_returns is a pandas Series.

    Parameters:
    pnl - A pandas Series representing period percentage returns.

    Returns:
    drawdown, duration - Highest peak-to-trough drawdown and duration.
    """

    # Calculate the cumulative returns curve 
    # and set up the High Water Mark
    # Then create the drawdown and duration series
    hwm = [0]
    eq_idx = equity_curve.index
    drawdown = pd.Series(index = eq_idx, dtype=float)
    duration = pd.Series(index = eq_idx, dtype=float)

    # Loop over the index range
    for t in range(1, len(eq_idx)):
        cur_hwm = max(hwm[t-1], equity_curve.iloc[t])
        hwm.append(cur_hwm)
        drawdown.iloc[t]= hwm[t] - equity_curve.iloc[t]
        duration.iloc[t]= 0 if drawdown.iloc[t] == 0 else duration.iloc[t-1] + 1
    return drawdown.max(), duration.max()