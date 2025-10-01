import streamlit as st
import backtester.metrics.dashboard._util as utils

st.set_page_config(layout="wide")
st.title("Performance Analysis")

if "sharpe_window" not in st.session_state:
  st.session_state["sharpe_window"] = "6M"

col1, col2 = st.columns([0.8, 0.2]) 

with col1:
  st.header(f"{st.session_state.sharpe_window} Rolling Sharpe")
  st.plotly_chart(utils.rolling_sharpe(st.session_state.df, st.session_state.arguments["interval"], st.session_state.sharpe_window), config={"width":"stretch"})
with col2:
  sharpe_window = st.selectbox(
    "Rolling Sharpe Duration Window",
    ("3M", "6M", "12M"),
    index=1,
    key="sharpe_window"
  )