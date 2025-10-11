import streamlit as st
import plotly.express as px
import backtester.metrics.dashboard._util as utils
import pandas as pd
import plotly.graph_objects as go

st.set_page_config(
    layout="wide",
    page_title="Risk Analysis"
)
st.title("Risk Analysis")
st.info(
    """
    Visualize the periods when the strategy was losing money from its peak.
    
    - **How to Use**: Click on a point in the Equity Curve during a dip to select and highlight that drawdown period across all charts. Use the "Clear Selection" button to reset.
    - **Duration vs. Magnitude**: The **Underwater Plot** shows how *long* the strategy stayed below its previous peak. The **Drawdown Plot** shows how *deep* the losses were.
    - **Worst Events**: The table at the bottom details the top 5 most severe drawdowns, allowing you to quantify the historical worst-case scenarios.
    """
)

if "selected_period" not in st.session_state:
  st.session_state.selected_period = None
if "var_method" not in st.session_state:
  st.session_state.var_method = "Historical"

# Perform calculations
drawdown_df = utils.calculate_drawdowns(st.session_state.df)
top_drawdowns = utils.find_top_drawdowns(drawdown_df)

if st.session_state.var_method == "Historical":
  var_95 = utils.get_historical_var(st.session_state.df, 0.95)
  var_99 = utils.get_historical_var(st.session_state.df, 0.99)
else:
  var_95 = utils.get_parametric_var(st.session_state.df, 0.95)
  var_99 = utils.get_parametric_var(st.session_state.df, 0.99)

##### Value at Risk #####
st.header("Value at Risk")
col_var1, col_var2, col_var3 = st.columns([0.4,0.4,0.2])
with col_var1:
    st.metric("Daily VaR (95%)", f"{var_95:.3f}%")
    st.caption("There is a 5% chance of losing more than this percentage in a single day.")
with col_var2:
    st.metric("Daily VaR (99%)", f"{var_99:.3f}%")
    st.caption("There is a 1% chance of losing more than this percentage in a single day.")
with col_var3:
  st.segmented_control(
    "Method",
    options=["Historical","Parametric"],
    selection_mode="single",
    key="var_method"
  )


##### Drawdown #####
#Equity Graph
fig_equity = go.Figure()
fig_equity.add_trace(
    go.Scatter(
        x=drawdown_df.index, 
        y=drawdown_df["equity_curve"], 
        mode="markers+lines",
        line=dict(
            color='rgba(3, 52, 110, 1.0)',
            width=2
        ),
        marker=dict(color='rgba(135, 206, 250, 0.0)')
    )
)
fig_equity.update_traces(
    hovertemplate="<b>Date</b>: %{x|%Y-%m-%d}<br><b>Equity</b>: %{y:.2f}x<br><extra></extra>"
)
fig_equity.update_layout(title_text='Equity Curve')


# Underwater Graph
fig_underwater = px.area(
        drawdown_df, 
        x=drawdown_df.index, 
        y="drawdown_percent",
        title="Time Spent Below High-Water Mark",
        labels={"drawdown_percent": "Drawdown (%)", "index": "Date"},
        color_discrete_sequence=['#FF6A6A'] # A reddish color for the area
    )   
# Customize the hover tooltip to focus on duration
fig_underwater.update_traces(
    hovertemplate="<b>Date</b>: %{x|%Y-%m-%d}<br><b>Drawdown</b>: %{y:.2f}%<br><b>Days Underwater</b>: %{customdata[0]}<extra></extra>",
    customdata=drawdown_df[['days_underwater']]
)
fig_underwater.update_layout(yaxis_title="Drawdown from Peak (%)", yaxis_ticksuffix="%")


# Create the drawdown plot as a line chart
fig_drawdown = px.line(
  drawdown_df, 
  x=drawdown_df.index, 
  y="drawdown_percent",
  title="Peak-to-Trough Drawdowns",
  labels={"drawdown_percent": "Drawdown (%)", "index": "Date"},
  color_discrete_sequence=['#1f77b4'] # A standard blue
)
# Customize hover tooltip to focus on magnitude
fig_drawdown.update_traces(
  hovertemplate="<b>Date</b>: %{x|%Y-%m-%d}<br><b>Drawdown</b>: %{y:.2f}%<br><b>Max Drawdown</b>: %{customdata[0]}<extra></extra>",
  customdata=drawdown_df[['max_drawdown']]
)
fig_drawdown.update_layout(yaxis_title="Drawdown from Peak (%)", yaxis_ticksuffix="%")


def onselect():
  selected_point = st.session_state.fig_equity_events
  if selected_point["selection"]["points"]:
    clicked_date = pd.to_datetime(selected_point["selection"]["points"][0]["x"])
    peak, recovery = utils.find_drawdown_period(clicked_date, drawdown_df)
    if peak and recovery:
        st.session_state.selected_period = {'start': peak, 'end': recovery}
    else: # If user clicks on a non-drawdown area
        st.session_state.selected_period = None

# --- Add Highlighting if a period is selected ---
if st.session_state.selected_period:
  start = st.session_state.selected_period['start']
  end = st.session_state.selected_period['end']
  
  # This function adds the vertical rectangle to any figure
  def add_highlight_shape(fig):
      fig.add_vrect(
          x0=start, x1=end,
          fillcolor="grey", opacity=0.25,
          layer="below", line_width=0,
      )
  add_highlight_shape(fig_equity)
  add_highlight_shape(fig_underwater)
  add_highlight_shape(fig_drawdown)


# --- Visualizations ---


colA, colB = st.columns([0.8, 0.2])
with colA:
  st.header("Drawdown")
with colB:
  st.write("") # Spacer
  st.write("") # Spacer
  if st.button("Clear Selection", width="stretch"):
      st.session_state.selected_period = None
      st.rerun()

# Use the first chart to capture events
st.plotly_chart(fig_equity, on_select=onselect, key="fig_equity_events", selection_mode="points")

col1, col2 = st.columns(2)

with col1:
  st.subheader("Underwater Plot")
  st.caption("Duration")
  st.plotly_chart(fig_underwater, config={"width":"stretch"})
with col2:
  st.subheader("Drawdown Plot")
  st.caption("Magnitude")
  # Add annotations for the top drawdown
  for i, row in top_drawdowns.head(1).iterrows(): # Annotate only the worst one to keep it clean
      fig_drawdown.add_annotation(
          x=row['Trough Date'], y=float(row['Max Drawdown %'].strip('%')),
          text=f"Worst DD: {row['Max Drawdown %']}",
          showarrow=True, arrowhead=2, arrowcolor="red",
          ax=-40, ay=-40,
          bgcolor="white"
      )
  st.plotly_chart(fig_drawdown, config={"width":"stretch"})


st.header("Top 5 Drawdown Periods")
st.markdown("This table provides context for the charts above, detailing the worst drawdown events.")
st.dataframe(top_drawdowns, width="stretch", hide_index=True)