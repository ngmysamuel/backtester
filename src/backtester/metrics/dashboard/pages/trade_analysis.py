import streamlit as st
import backtester.metrics.dashboard._util as utils

st.set_page_config(
    layout="wide",
    page_title="Trade Analysis"
)
st.title("Trade Analysis")

st.info(
    """
    This page provides a detailed log of every trade executed by the strategy.
    - This view is useful for debugging the strategy's behavior on specific dates or for a particular asset.
    """
)

st.header("Trades")
trades_df = utils.get_trades(st.session_state.df)

if trades_df.empty:
    st.warning("No trades were executed during this backtest.")
else:
    st.dataframe(trades_df, hide_index=True, column_config={
      "Quantity":st.column_config.TextColumn("Quantity")
    })

st.header("PNL")
st.dataframe(utils.book_trades(st.session_state.df), hide_index=True, column_config={
      "Quantity":st.column_config.TextColumn("Quantity"),
      "EOD Nett Position":st.column_config.TextColumn("EOD Nett Position"),
      "Entry Price":st.column_config.NumberColumn("Entry Price", format="dollar"),
      "Exit Price":st.column_config.NumberColumn("Exit Price", format="dollar"),
      "PnL":st.column_config.NumberColumn("PnL", format="$%d"),
      "Return":st.column_config.NumberColumn("Return", format="%.2f%%"),
    })