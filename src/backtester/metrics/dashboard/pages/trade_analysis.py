import streamlit as st
import backtester.metrics.dashboard._util as utils

st.set_page_config(
    layout="wide",
    page_title="Trade Analysis"
)
st.title("Trade Analysis")

st.info(
    """
    This page provides a detailed log of every trade executed by the strategy, grouped by date.
    - This view is useful for debugging the strategy's behavior on specific dates or for a particular asset.
    """
)

st.header("Trades")
trades_df = utils.get_trades(st.session_state.df)

if trades_df.empty:
    st.warning("No trades were executed during this backtest.")
else:
    st.dataframe(trades_df, hide_index=True, column_config={"Quantity":st.column_config.TextColumn("Quantity")})