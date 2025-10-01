import streamlit as st
import backtester.metrics.dashboard._util as utils
from millify import millify

st.set_page_config(layout="wide")
st.title("Performance Analysis")

if "sharpe_window" not in st.session_state:
  st.session_state["sharpe_window"] = "6M"
if "vol_window" not in st.session_state:
  st.session_state["vol_window"] = "6M"
if "histo_window" not in st.session_state:
  st.session_state["histo_window"] = "Monthly"
if "heatmap_window" not in st.session_state:
  st.session_state["heatmap_window"] = "Monthly"

col1, col2 = st.columns([0.8, 0.2]) 
with col1:
  st.header(f"Sharpe - {st.session_state.sharpe_window} Rolling")
  st.plotly_chart(utils.rolling_sharpe(st.session_state.df, st.session_state.arguments["interval"], st.session_state.sharpe_window), config={"width":"stretch"})
with col2:
  sharpe_window = st.selectbox(
    "Rolling Sharpe Duration Window",
    ("3M", "6M", "12M"),
    index=1,
    key="sharpe_window"
  )


col3, col4 = st.columns([0.8, 0.2]) 
with col3:
  st.header(f"Volatility - {st.session_state.vol_window} Rolling")
  st.plotly_chart(utils.rolling_volitility(st.session_state.df, st.session_state.arguments["interval"], st.session_state.vol_window), config={"width":"stretch"})
with col4:
  vol_window = st.selectbox(
    "Rolling Volatility Duration Window",
    ("3M", "6M", "12M"),
    index=1,
    key="vol_window"
  )


fig, kurtosis, skewness = utils.returns_histogram(st.session_state.df, st.session_state.arguments["interval"], st.session_state.histo_window)

col5, col6 = st.columns([0.8, 0.2]) 
with col5:
  st.header(f"Distribution of {st.session_state.histo_window} Returns")
  st.plotly_chart(fig)
with col6:
  histo_window = st.selectbox(
    "Distribution Windows",
    ("Weekly", "Monthly", "Quaterly", "Yearly"),
    index=1,
    key="histo_window"
  )
  st.metric("Excess Kurtosis", millify(kurtosis, precision=3))
  st.caption("A higher value indicates a greater possibility of outlier returns")
  st.metric("Skewness", millify(skewness, precision=3))
  st.caption("A positive value indicates many small losses and a few very large winners")


fig = utils.returns_heatmap(st.session_state.df, st.session_state.arguments["interval"], st.session_state.heatmap_window)

col7, col8 = st.columns([0.8, 0.2])
with col7:
  st.header(f"{st.session_state.heatmap_window} Returns - Heatmap (%)")
  st.plotly_chart(fig)
# with col8:
#   heatmap_window = st.selectbox(
#     "Distribution Windows",
#     ("Weekly", "Monthly", "Quaterly", "Yearly"),
#     index=1,
#     key="heatmap_window"
#   )