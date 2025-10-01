import pandas as pd
import numpy as np
import plotly.express as px
import plotly
from millify import millify

DAYS_IN_YEAR = 365.0
MINUTES_IN_HOUR = 60.0
TRD_HOURS_IN_DAY = 6.5
TRD_DAYS_IN_YEAR = 252.0
STRING_TO_RESAMPLE_WINDOW = {
  "Weekly": "W",
  "Monthly": "ME",
  "Quaterly": "QE",
  "Yearly": "YE",
}

def get_annualization_factor(interval: str) -> float:
    """
    Calculates the annualization factor based on the data's frequency,
    1m, 2m, 5m, 15m, 30m, 60m, 90m, 1h, 1d, 5d, 1wk, 1mo, 3mo (to create enum)
    """
    match interval:
      case "1m":
        return MINUTES_IN_HOUR * TRD_HOURS_IN_DAY * TRD_DAYS_IN_YEAR
      case "2m":
        return (MINUTES_IN_HOUR / 2) * TRD_HOURS_IN_DAY * TRD_DAYS_IN_YEAR
      case "15m":
        return (MINUTES_IN_HOUR / 15) * TRD_HOURS_IN_DAY * TRD_DAYS_IN_YEAR
      case "30m":
        return (MINUTES_IN_HOUR / 30) * TRD_HOURS_IN_DAY * TRD_DAYS_IN_YEAR
      case "60m" | "1h":
        return TRD_HOURS_IN_DAY * TRD_DAYS_IN_YEAR
      case "90m":
        return (TRD_HOURS_IN_DAY / 1.5) * TRD_DAYS_IN_YEAR
      case "1d":
        return TRD_DAYS_IN_YEAR
      case "5d":
        return TRD_DAYS_IN_YEAR / 5
      case "1mo":
        return 12
      case "3mo":
        return 4
      case _:
        raise ValueError(f"{interval} is not supported")

def get_total_return(df: pd.DataFrame) -> float:
  """Calculates the total return from an equity curve."""
  return (df.iloc[-1]["equity_curve"] - 1) * 100

def get_sharpe(df: pd.DataFrame, interval: str) -> float:
  """Calculates the Sharpe ratio with a dynamic annualization factor."""
  annualization_factor = get_annualization_factor(interval)
  returns = df["returns"].dropna()
  if np.std(returns, ddof=1) == 0:
      return 0.0 # Avoid division by zero if no volatility
  return np.sqrt(annualization_factor) * (np.mean(returns) / np.std(returns, ddof=1))

def get_cagr(df: pd.DataFrame, interval: str) -> float:
  """Calculates the Compound Annual Growth Rate."""
  annualization_factor = get_annualization_factor(interval)
  pv = df.iloc[0]["total"]
  fv = df.iloc[-1]["total"]
  years = len(df) / annualization_factor
  if years == 0:
      return 0.0
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

def get_calmar(df: pd.DataFrame, interval: str) -> float:
  """Calculates the Calmar ratio."""
  cagr = get_cagr(df, interval)
  max_drawdown, _, _, _, _ = get_max_drawdown(df)
  if max_drawdown == 0:
      return np.inf # or 0.0, depending on convention
  return cagr / max_drawdown

def get_equity_curve(df: pd.DataFrame) -> plotly.graph_objs.Figure:
  """Returns the equity curve series from the DataFrame."""
  fig = px.line(df, x=df.index, y="equity_curve")
  fig.update_layout(xaxis_title="Date", yaxis_title="Returns")
  return fig


def rolling_sharpe(df: pd.DataFrame, interval: str, window: str) -> plotly.graph_objs.Figure:
  match window:
    case "3M":
      window = 63
    case "6M":
      window = 126
    case "12M":
      window = 252
    case _:
      window = 126
  annualization_factor = get_annualization_factor(interval)
  rolling_sharpe = df["returns"].rolling(window).apply(
    lambda x: np.sqrt(annualization_factor) * (np.mean(x) / np.std(x, ddof=1)) if np.std(x, ddof=1) != 0 else 0.0
  )
  fig = px.line(rolling_sharpe)
  fig.update_layout(xaxis_title="Date", yaxis_title="Rolling Sharpe", showlegend=False)
  return fig

def rolling_volitility(df: pd.DataFrame, interval: str, window: str) -> plotly.graph_objs.Figure:
  match window:
    case "3M":
      window = 63
    case "6M":
      window = 126
    case "12M":
      window = 252
    case _:
      window = 126
  annualization_factor = get_annualization_factor(interval)
  rolling_volitility = df["returns"].rolling(window).apply(lambda x: np.sqrt(annualization_factor) * np.std(x, ddof=1))
  fig = px.line(rolling_volitility)
  fig.update_layout(xaxis_title="Date", yaxis_title="Rolling Volatility", showlegend=False)
  return fig

def returns_histogram(df: pd.DataFrame, interval: str, window: str):
  if interval == "5d":
    interval = "Weekly"
  elif interval == "1mo":
    interval = "Monthly"
  elif interval == "3mo":
    interval = "Quaterly"

  if interval != window:
    window = STRING_TO_RESAMPLE_WINDOW.get(window, "ME")
    ohlc_data = df["equity_curve"].resample(window).ohlc()
    ohlc_data["returns"] = ((ohlc_data["close"] - ohlc_data["open"]) / ohlc_data["close"]) * 100
    fig = px.histogram(ohlc_data, x="returns")
    kurtosis = ohlc_data["returns"].kurtosis()
    skewness = ohlc_data["returns"].skew()
    return fig, kurtosis, skewness
  else:
    fig = px.histogram(df, x="returns")
    kurtosis = df["returns"].kurtosis()
    skewness = df["returns"].skew()
    return fig, kurtosis, skewness

def returns_heatmap(df: pd.DataFrame, interval: str, window: str):
  window = STRING_TO_RESAMPLE_WINDOW.get(window, "ME")
  ohlc_data = df["equity_curve"].resample(window).ohlc()
  ohlc_data["returns"] = ((ohlc_data["close"] - ohlc_data["open"]) / ohlc_data["close"]) * 100
  ohlc_data["returns"] = ohlc_data["returns"].apply(lambda x: float(millify(x, precision=2)))
  ohlc_data["year"] = ohlc_data.index.year
  ohlc_data["month"] = ohlc_data.index.month
  ohlc_data["month_name"] = ohlc_data.index.strftime("%b")
  data = pd.pivot_table(ohlc_data, values="returns", index="year", columns="month_name")
  data = data[ohlc_data["month_name"].sort_values(key=lambda x: pd.to_datetime(x,format="%b").dt.month).drop_duplicates()]
  # return data
  return px.imshow(data.values, x=data.columns, y=data.index, text_auto=True)