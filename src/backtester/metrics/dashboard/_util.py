import pandas as pd
import numpy as np
import plotly.express as px
import plotly
from millify import millify
from scipy.stats import norm
from collections import deque, defaultdict
import plotly.graph_objects as go

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
  trades_df['order'] = trades_df['order'].str.replace(" @ ", " ")
  trades_df = trades_df[trades_df['order'] != '']

  # Split the trade string into components: Direction, Quantity, Ticker
  parts = trades_df['order'].str.split(n=3, expand=True)
  trades_df['Direction'] = parts[0]
  trades_df['Quantity'] = pd.to_numeric(parts[1])
  trades_df['Ticker'] = parts[2]
  trades_df['Unit Price'] = "$" + parts[3]

  # Format the final DataFrame for display
  trades_df = trades_df.reset_index().rename(columns={'timestamp': 'Date'})

  return trades_df[['Date', 'Direction', 'Quantity', 'Ticker', 'Unit Price']]

def book_trades(df: pd.DataFrame):
  """
  FIFO method to book trades individually. 
  Args
  1. df - df has to be output from get_trades(), a method above
  Returns
  1. return_df - a df with the pnl arising from every new buy/sell order
  that has been closed with their corresponding sell/buy
  """
  df["Unit Price"] = df["Unit Price"].str[1:].astype(float)
  df["Date"] = df["Date"].dt.strftime("%Y-%m-%d")
  traded_tickers = df["Ticker"].unique()
  shorts = {ticker: deque() for ticker in traded_tickers}
  longs = {ticker: deque() for ticker in traded_tickers}
  net_positions = defaultdict(int)
  closed_trades = []
  for _, trade in df.iterrows():
    ticker = trade["Ticker"]
    unit_price = trade["Unit Price"]
    trade_date = trade["Date"]
    trade_direction = trade["Direction"]
    outstanding_quantity = trade["Quantity"]
    if trade_direction == "BUY":
      net_positions[ticker] += trade["Quantity"]
      while outstanding_quantity > 0:
        if shorts[ticker]: # there exists someting in the SHORT deque for that ticker - COVER SHORT
          earliest_short = shorts[ticker][0]
          px_diff = earliest_short["price"] - unit_price
          traded_quantity = min(outstanding_quantity, earliest_short["quantity"])
          pnl = px_diff * traded_quantity
          return_pct = (px_diff / earliest_short["price"]) * 100
          closed_trades.append({
            "ticker": ticker, "entry_date": earliest_short["date"], "exit_date": trade_date, 
            "type": "BUY", "quantity": traded_quantity, "nett position": net_positions[ticker],
            "entry_price": earliest_short["price"], "exit_price": unit_price,
             "pnl": pnl, "return_pct": return_pct,
          })
          if earliest_short["quantity"] > outstanding_quantity: # entirely cover BUY
            earliest_short["quantity"] -= outstanding_quantity
            outstanding_quantity = 0
          else: # partial cover BUY
            outstanding_quantity -= earliest_short["quantity"]
            shorts[ticker].popleft()
        else: # not short / no longer short - add to BUY
          longs[ticker].append({
            "price": unit_price, "date": trade_date, "quantity": outstanding_quantity
          })
          outstanding_quantity = 0
    elif trade_direction == "SELL":
      net_positions[ticker] -= trade["Quantity"]
      while outstanding_quantity > 0:
        if longs[ticker]: # there exists someting in the LONG deque for that ticker - SELL
          earliest_long = longs[ticker][0]
          px_diff = unit_price - earliest_long["price"]
          traded_quantity = min(outstanding_quantity, earliest_long["quantity"])
          pnl = px_diff * traded_quantity
          return_pct = (px_diff / earliest_long["price"]) * 100
          closed_trades.append({
            "ticker": ticker, "entry_date": earliest_long["date"], "exit_date": trade_date,
            "type": "SELL", "quantity": traded_quantity, "nett position": net_positions[ticker],
            "entry_price": earliest_long["price"], "exit_price": unit_price,
            "pnl": pnl, "return_pct": return_pct,
          })
          if earliest_long["quantity"] > outstanding_quantity: # entirely cover SELL
            earliest_long["quantity"] -= outstanding_quantity
            outstanding_quantity = 0
          else: # partial cover SELL
            outstanding_quantity -= earliest_long["quantity"]
            longs[ticker].popleft()
        else: # not long / no longer long - add to SHORT
          shorts[ticker].append({
            "price": unit_price, "date": trade_date, "quantity": outstanding_quantity
          })
          outstanding_quantity = 0
  return_df = pd.DataFrame(closed_trades)
  return_df.columns = ["Ticker", "Entry Date", "Exit Date", "Direction", "Quantity", "EOD Nett Position", "Entry Price", "Exit Price", "PnL", "Return"]
  return return_df

def plot_equity_curve_with_trades(ticker: str, df_trades: pd.DataFrame, df_equity: pd.DataFrame):
  """
  Returns a line graph of the equity curve as well as the trades made superimposed over it. 
  Args
  1. ticker - a string of the ticker. Can be 'All' to include all ticker trades
  2. df_trades - dataframe of the closed trades; from the book_trades() method
  3. df_equity - dataframe with the equity curve
  """
  df_equity = df_equity[["equity_curve"]]
  y_min, y_max = df_equity["equity_curve"].min(), df_equity["equity_curve"].max()
  fig = px.line(df_equity, x=df_equity.index, y="equity_curve")

  if ticker != "All":
    df_trades = df_trades[df_trades["Ticker"] == ticker]

  # Use flags to add legend items only once
  legend_added = {'BUY': False, 'SELL': False}

  for _, trade in df_trades.iterrows():
    direction = trade["Direction"]
    ticker = trade["Ticker"]
    trade_color = "#19f505" if direction == "BUY" else "#eb4034"
    hover_text = f'{trade["Date"].strftime("%Y-%m-%d")}: {direction} {int(trade["Quantity"])} {ticker} @ {trade["Unit Price"]}'
    
    show_legend_for_this_trace = not legend_added[direction]

    fig.add_trace(go.Scatter(
        x=[trade["Date"], trade["Date"]],
        y=[y_min, y_max],
        mode='lines',
        line=dict(color=trade_color, width=2, dash='dot'),
        name=direction,
        hoverinfo='text', # Disable hover on the thin visible line
        hovertext=hover_text,
        legendgroup=direction.lower(),
        showlegend=show_legend_for_this_trace,
        opacity=0.7
    ))

    if show_legend_for_this_trace:
        legend_added[direction] = True
  
  fig.update_layout(
      title_text='Equity Curve with Trades',
      xaxis_title='Date',
      yaxis_title='Equity',
      legend_title='Trade Direction'
  )
        
  return fig


def plot_stacked_pnl_by_holding_period(ticker: str, df: pd.DataFrame):
    """
    Creates a stacked bar chart showing Gross Profit vs. Gross Loss for each bin.
    """
    if ticker != "All":
      df = df[df["Ticker"] == ticker]

    df["Holding Period"] = (pd.to_datetime(df["Exit Date"]) - pd.to_datetime(df["Entry Date"])).dt.days
    bins = [0, 5, 10, 20, 30, np.inf]
    labels = ['1-5 Days', '6-10 Days', '11-20 Days', '21-30 Days', '30+ Days']
    df['period_bin'] = pd.cut(df['Holding Period'], bins=bins, labels=labels, right=False)
    
    # Calculate Gross Profit and Gross Loss for each bin
    gross_profit = df[df['PnL'] > 0].groupby('period_bin', observed=True)['PnL'].sum()
    gross_loss = df[df['PnL'] < 0].groupby('period_bin', observed=True)['PnL'].sum()
    
    # Combine into a single DataFrame for plotting
    summary = pd.DataFrame({'Gross Profit': gross_profit, 'Gross Loss': gross_loss}).fillna(0)
    
    fig = go.Figure()
    
    # Add Gross Profit bars (green)
    fig.add_trace(go.Bar(
        x=summary.index,
        y=summary['Gross Profit'],
        name='Gross Profit',
        marker_color='#2ca02c',
        hovertemplate="<b>%{x}</b><br>Gross Profit: $%{y:,.2f}<extra></extra>"
    ))
    
    # Add Gross Loss bars (red)
    fig.add_trace(go.Bar(
        x=summary.index,
        y=summary['Gross Loss'],
        name='Gross Loss',
        marker_color='#d62728',
        hovertemplate="<b>%{x}</b><br>Gross Loss: $%{y:,.2f}<extra></extra>"
    ))
    
    fig.update_layout(
        barmode='relative', # This stacks positive and negative values from the zero line
        title_text='Gross Profit vs. Gross Loss by Holding Period',
        xaxis_title='Holding Period Bin',
        yaxis_title='P&L ($)',
        legend_title='Metric'
    )
    
    return fig