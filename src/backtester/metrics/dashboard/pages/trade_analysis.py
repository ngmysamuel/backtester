import streamlit as st
import backtester.metrics.dashboard._util as utils

st.set_page_config(layout="wide", page_title="Trade Analysis")
st.title("Trade Analysis")

st.info(
    """
    This page offers a granular view of the backtest's trade-level performance.
    - **Trade Log:** Examine every transaction with details on ticker, direction, quantity, and price.
    - **Performance Visualization:** Analyze the timing and impact of trades on the equity curve.
    - **Profit & Loss:** Review the PnL for each closed trade to understand sources of return.
    - **Asset-Specific Analysis:** Use the filters to isolate and analyze performance for individual tickers.
    """
)


st.header("Trade Log")
trades_df = utils.get_trades(st.session_state.df)

if "trade_analysis_ticker_trades" not in st.session_state:
    st.session_state.trade_analysis_ticker_trades = "All"
if "trade_analysis_ticker_pnl" not in st.session_state:
    st.session_state.trade_analysis_ticker_pnl = "All"

if trades_df.empty:
    st.warning("No trades were executed during this backtest.")
else:
    st.dataframe(trades_df, hide_index=True, column_config={"Quantity": st.column_config.TextColumn("Quantity"), "Date": st.column_config.DateColumn("Date", format="DD MMM YYYY")})
col1, col2 = st.columns([0.9, 0.1])
with col1:
    st.plotly_chart(utils.plot_equity_curve_with_trades(st.session_state.trade_analysis_ticker_trades, trades_df, st.session_state.df))
with col2:
    trade_analysis_ticker_trades = st.selectbox("Filter by Ticker", ["All"] + [*trades_df["Ticker"].unique()], index=0, key="trade_analysis_ticker_trades")

st.header("Closed Trades Profit and Loss")
pnl = utils.book_trades(trades_df)
st.dataframe(
    pnl,
    hide_index=True,
    column_config={
        "Quantity": st.column_config.TextColumn("Quantity"),
        "EOD Nett Position": st.column_config.TextColumn("EOD Nett Position"),
        "Entry Price": st.column_config.NumberColumn("Entry Price", format="dollar"),
        "Exit Price": st.column_config.NumberColumn("Exit Price", format="dollar"),
        "PnL": st.column_config.NumberColumn("PnL", format="$%d"),
        "Return": st.column_config.NumberColumn("Return", format="%.2f%%"),
    },
)
col1, col2 = st.columns([0.9, 0.1])
with col1:
    st.plotly_chart(utils.plot_stacked_pnl_by_holding_period(st.session_state.trade_analysis_ticker_pnl, pnl))
with col2:
    trade_analysis_ticker_pnl = st.selectbox("Filter by Ticker", ["All"] + [*trades_df["Ticker"].unique()], index=0, key="trade_analysis_ticker_pnl")
