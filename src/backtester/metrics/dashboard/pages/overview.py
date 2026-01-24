import streamlit as st
from millify import millify
import pandas as pd
from backtester import ROOT_DIR
import backtester.metrics.dashboard._util as utils
import os

st.set_page_config(layout="wide")
output_path = ROOT_DIR
if "job_id" in st.session_state:
    output_path = f"{st.session_state["path_prefix"]}{st.session_state["session_id"]}/{st.session_state["job_id"]}"

@st.cache_resource
def get_tearsheet():
    return open(os.path.join(output_path, "strategy_report.html"), "r")

tearsheet = get_tearsheet()

colTitle, colDwl = st.columns([0.8, 0.2]) 
with colTitle:
    st.title('Backtest Performance Dashboard')
with colDwl:
    st.download_button(
        label="Download Tearsheet",
        data=tearsheet,
        file_name="strategy_report.html",
        mime="text/html",
        icon=":material/download:",
        help="Downloads a tearsheet with comprehensive metrics for viewing on the go",
        type="primary"
    )

# --- Data Loading ---
@st.cache_data
def load_data():
    """Loads the equity curve data from the CSV file."""
    try:
        df = pd.read_csv(f"{output_path}/equity_curve.csv")
        df["timestamp"] = pd.to_datetime(df["timestamp"])
        df = df.set_index("timestamp")
        return df
    except FileNotFoundError:
        st.error("equity_curve.csv not found. Please run a backtest first.")
        return None

if "df" not in st.session_state:
    st.session_state.df = load_data()

if st.session_state.df is not None:
    # --- Key Performance Indicators (KPIs) ---
    st.header("Key Performance Indicators")
    col1, col2, col3, col4 = st.columns(4)
    with col1:
        st.metric("Total Return", f"{millify(utils.get_total_return(st.session_state.df), precision=2)}%")
    with col2:
        st.metric("Sharpe Ratio", f"{millify(utils.get_sharpe(st.session_state.df, st.session_state.arguments["interval"]), precision=3)}")
    with col3:
        st.metric("CAGR", f"{millify(utils.get_cagr(st.session_state.df, st.session_state.arguments["interval"]), precision=3)}%")
    with col4:
        st.metric("Calmar Ratio", f"{millify(utils.get_calmar(st.session_state.df, st.session_state.arguments["interval"]), precision=3)}")

    # --- Drawdown Analysis ---
    st.header("Drawdown Analysis")
    max_drawdown, max_drawdown_date, longest_streak, longest_start, longest_end = utils.get_max_drawdown(st.session_state.df)
    
    col5, col6 = st.columns(2)
    with col5:
        st.metric("Max Drawdown", f"{millify(max_drawdown, precision=2)}%")
        st.caption(f"Lowest point occurred on: {max_drawdown_date}")
    
    with col6:
        st.metric("Longest Drawdown Period", f"{longest_streak} intervals")
        st.caption(f"From {longest_start} to {longest_end}")

    # --- Equity Curve Chart ---
    st.header("Equity Curve")
    st.plotly_chart(utils.get_equity_curve(st.session_state.df), config={"width":"stretch"})
