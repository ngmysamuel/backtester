import streamlit as st
import backtester.metrics.dashboard._util as utils

st.set_page_config(layout="wide")
st.title("Performance Analysis")

sharpe_window = "6M"
st.header(f"{sharpe_window} Rolling Sharpe")
sharpe_window = st.selectbox(
    "Rolling Sharpe Duration Window",
    ("3M", "6M", "12M"),
)
st.plotly_chart(utils.rolling_sharpe(st.session_state.df, st.session_state.arguments["interval"], sharpe_window), config={"width":"stretch"})