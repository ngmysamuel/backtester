import pandas as pd
import numpy as np
import plotly.express as px
import plotly

DAYS_IN_YEAR = 365

def get_annualization_factor(df: pd.DataFrame) -> float:
    """Calculates the annualization factor based on the data frequency."""
    if df.empty:
        return 252.0  # Default to daily if no data
    years_span = (df.index[-1] - df.index[0]).days / DAYS_IN_YEAR
    if years_span == 0:
        return 252.0 # Avoid division by zero for single-day data
    
    return len(df) / years_span

def get_total_return(df: pd.DataFrame) -> float:
  """Calculates the total return from an equity curve."""
  return (df.iloc[-1]["equity_curve"] - 1) * 100

def get_sharpe(df: pd.DataFrame) -> float:
  """Calculates the Sharpe ratio with a dynamic annualization factor."""
  annualization_factor = get_annualization_factor(df)
  returns = df["returns"].dropna()
  if returns.std() == 0:
      return 0.0 # Avoid division by zero if no volatility
  return np.sqrt(annualization_factor) * np.mean(returns) / np.std(returns, ddof=1)

def get_cagr(df: pd.DataFrame) -> float:
  """Calculates the Compound Annual Growth Rate."""
  pv = df.iloc[0]["total"]
  fv = df.iloc[-1]["total"]
  years = (df.index[-1] - df.index[0]).days / DAYS_IN_YEAR
  if years == 0:
      return 0.0 # No growth if no time has passed
  cagr = (fv / pv) ** (1 / years)
  return (cagr - 1) * 100

def get_max_drawdown(df: pd.DataFrame):
  """
  Calculates the maximum drawdown, its date, and the start, end, and duration
  of the longest drawdown period using a vectorized pandas approach.
  """
  # Find max drawdown and the date it happened on
  equity_curve = df[["equity_curve"]].copy()
  equity_curve["hwm"] = equity_curve["equity_curve"].cummax()
  equity_curve["dd_percent"] = (equity_curve["hwm"] - equity_curve["equity_curve"]) / equity_curve["hwm"] * 100
  
  max_drawdown = equity_curve["dd_percent"].max()
  max_drawdown_date = equity_curve["dd_percent"].idxmax()
  
  # Find the longest drawdown - start date to end date
  in_drawdown = equity_curve["dd_percent"] > 0 # if neg, means below HWM, hence, in drawdown
  drawdown_groups = (in_drawdown != in_drawdown.shift()).cumsum() # shifting by 1 exposes where the status shifts from one to the other. Using cumsum() generates an unqiue ID after each shift
  drawdown_lengths = drawdown_groups[in_drawdown].value_counts() # count(*) GROUP BY group IDs

  if drawdown_lengths.empty:
      # No drawdown occurred
      return max_drawdown, max_drawdown_date.strftime('%d %b, %Y'), 0, df.index[0].strftime('%d %b, %Y'), df.index[0].strftime('%d %b, %Y')

  longest_streak = drawdown_lengths.max()
  longest_dd_group_id = drawdown_lengths.idxmax()
  
  longest_dd_period = equity_curve[drawdown_groups == longest_dd_group_id]
  
  # The peak is the day before the drawdown period starts
  start_date_loc = df.index.get_loc(longest_dd_period.index[0])
  peak_date_loc = max(0, start_date_loc - 1)
  longest_start = df.index[peak_date_loc]
  longest_end = longest_dd_period.index[-1]

  return (
      max_drawdown,
      max_drawdown_date.strftime('%d %b, %Y'),
      longest_streak,
      longest_start.strftime('%d %b, %Y'),
      longest_end.strftime('%d %b, %Y')
  )

def get_calmar(df: pd.DataFrame) -> float:
  """Calculates the Calmar ratio."""
  cagr = get_cagr(df)
  max_drawdown, _, _, _, _ = get_max_drawdown(df)
  if max_drawdown == 0:
      return np.inf # or 0.0, depending on convention
  return cagr / max_drawdown

def get_equity_curve(df: pd.DataFrame) -> plotly.graph_objs.Figure:
  """Returns the equity curve series from the DataFrame."""
  fig = px.line(df, x=df.index, y="equity_curve")
  fig.update_layout(xaxis_title="Date", yaxis_title="Returns")
  return fig