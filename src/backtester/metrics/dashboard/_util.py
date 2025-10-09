import pandas as pd
import numpy as np
import plotly.express as px
import plotly
from millify import millify
from scipy.stats import norm

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
  of the longest drawdown period.
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
  return px.imshow(data.values, x=data.columns, y=data.index, text_auto=True, color_continuous_scale="brbg", color_continuous_midpoint=0)

def calculate_drawdowns(df: pd.DataFrame) -> pd.DataFrame:
    """
    Calculates drawdown, high-water mark, and days since peak for an equity curve.
    """
    analysis_df = df.copy()
    analysis_df["hwm"] = analysis_df["equity_curve"].cummax()
    
    # The correct drawdown calculation is (current_value - peak_value) / peak_value
    analysis_df["drawdown_percent"] = (analysis_df["equity_curve"] - analysis_df["hwm"]) / analysis_df["hwm"] * 100
    
    # Identify periods when the strategy is "underwater"
    analysis_df["underwater"] = analysis_df["drawdown_percent"] < 0
    
    # Find the start of each drawdown period to calculate duration
    drawdown_starts = analysis_df[analysis_df["underwater"] & ~analysis_df["underwater"].shift(1, fill_value=False)].index
    
    # Map each drawdown period to its start date
    start_dates = pd.Series(index=analysis_df.index, dtype='datetime64[ns]')
    for start in drawdown_starts:
        end = analysis_df.index[analysis_df.index > start]
        if not any(~analysis_df.loc[end, 'underwater']):
            end_date = analysis_df.index[-1]
        else:
            end_date = analysis_df.loc[end, 'underwater'].idxmin()
        start_dates.loc[start:end_date] = start
    
    analysis_df['drawdown_start_date'] = start_dates.ffill()
    analysis_df["max_drawdown"] = analysis_df.groupby("drawdown_start_date")["drawdown_percent"].transform("min")
    analysis_df["max_drawdown"] = analysis_df.apply(lambda x: float(millify(x["max_drawdown"], precision=2)) if x["underwater"] else None, axis=1)
    analysis_df['days_underwater'] = (analysis_df.index - analysis_df['drawdown_start_date']).dt.days
    analysis_df["days_underwater"] = analysis_df.apply(lambda x: x["days_underwater"] if x["underwater"] else None, axis=1)
    
    return analysis_df

def find_top_drawdowns(df: pd.DataFrame, n: int = 5) -> pd.DataFrame:
    """Identifies and returns the top N drawdown periods."""
    drawdown_periods = []
    in_drawdown = False
    current_period = {}

    for date, row in df.iterrows():
        if not in_drawdown and row['underwater']:
            in_drawdown = True
            current_period = {
                'Peak Date': (df['equity_curve'].loc[:date] == row['hwm']).idxmax(),
                'Peak Value': row['hwm'],
                'Trough Date': date,
                'Trough Value': row['equity_curve'],
                'Max Drawdown %': row['drawdown_percent']
            }
        elif in_drawdown:
            if row['drawdown_percent'] < current_period['Max Drawdown %']:
                current_period['Trough Date'] = date
                current_period['Trough Value'] = row['equity_curve']
                current_period['Max Drawdown %'] = row['drawdown_percent']
            
            if not row['underwater']:
                in_drawdown = False
                current_period['Recovery Date'] = date
                current_period['Duration (days)'] = (current_period['Recovery Date'] - current_period['Peak Date']).days
                drawdown_periods.append(current_period)

    if in_drawdown: # Handle case where backtest ends in a drawdown
        current_period['Recovery Date'] = "Not Recovered"
        current_period['Duration (days)'] = (df.index[-1] - current_period['Peak Date']).days
        drawdown_periods.append(current_period)
        
    if not drawdown_periods:
        return pd.DataFrame()

    summary = pd.DataFrame(drawdown_periods).sort_values(by='Max Drawdown %').head(n)
    
    # Format date columns to strings for consistent typing and display
    for col in ['Peak Date', 'Trough Date', 'Recovery Date']:
        if col in summary.columns:
            summary[col] = summary[col].apply(lambda x: x.strftime('%d %b, %Y') if isinstance(x, pd.Timestamp) else x)

    summary['Max Drawdown %'] = summary['Max Drawdown %'].map('{:,.2f}%'.format)
    return summary.reset_index(drop=True)

def find_drawdown_period(clicked_date, df):
    """Finds the full start and end date of a drawdown given one date within it."""
    if clicked_date is None:
        return None, None
        
    period_info = df.loc[clicked_date]
    if not period_info['underwater']:
        return None, None

    start_date = period_info['drawdown_start_date']
    period_df = df[df['drawdown_start_date'] == start_date]
    end_date = period_df.index.max()

    return start_date, end_date

def get_historical_var(df: pd.DataFrame, confidence_level: float = 0.95) -> float:
    """
    Calculates the historical Value at Risk (VaR) at a given confidence level.
    """
    if 'returns' not in df.columns or df['returns'].dropna().empty:
        return 0.0
    
    # VaR is the quantile of the returns distribution
    var = df['returns'].quantile(1 - confidence_level)
    
    # Return as a positive percentage
    return abs(var * 100)

def get_parametric_var(df: pd.DataFrame, confidence_level: float = 0.95) -> float:
    """
    Calculates the parametric Value at Risk (VaR) at a given confidence level.
    """
    if 'returns' not in df.columns or df['returns'].dropna().empty:
        return 0.0
    z_score = norm.ppf(1 - confidence_level)
    mean = df["returns"].mean()
    sd = df["returns"].std()
    var = mean - (z_score * sd)
    return abs(var * 100)

def get_trades(df: pd.DataFrame):
  """
  Parses the 'order' column of the equity curve DataFrame to create a clean,
  structured log of all trades.
  """
  # Filter for rows that have order information and drop NaNs
  trades_df = df[df['order'].str.len() > 0][['order']].copy()
  if trades_df.empty:
      return pd.DataFrame(columns=['Date', 'Direction', 'Quantity', 'Ticker'])

  # Split the pipe-delimited string into a list of trades
  trades_df['order'] = trades_df['order'].str.split('|')

  # Create a new row for each trade in the list
  trades_df = trades_df.explode('order')

  # Clean up: remove leading/trailing whitespace and filter out empty strings
  trades_df['order'] = trades_df['order'].str.strip()
  trades_df = trades_df[trades_df['order'] != '']

  # Split the trade string into components: Direction, Quantity, Ticker
  parts = trades_df['order'].str.split(n=2, expand=True)
  trades_df['Direction'] = parts[0]
  trades_df['Quantity'] = pd.to_numeric(parts[1])
  trades_df['Ticker'] = parts[2]

  # Format the final DataFrame for display
  trades_df = trades_df.reset_index().rename(columns={'timestamp': 'Date'})
  trades_df['Date'] = trades_df['Date'].dt.strftime('%Y-%m-%d')

  return trades_df[['Date', 'Direction', 'Quantity', 'Ticker']]