import streamlit as st
import plotly.express as px
import backtester.metrics.dashboard._util as utils

# --- Page Configuration ---
st.set_page_config(
    layout="wide",
    page_title="Risk Analysis"
)
st.title("Risk Analysis")
st.info(
    """
    This dashboard provides an overview of the risks associated with the strategy.
    """
)


# Perform calculations
drawdown_df = utils.calculate_drawdowns(st.session_state.df)
top_drawdowns = utils.find_top_drawdowns(drawdown_df)

# --- Visualizations ---

col1, col2 = st.columns(2)

with col1:
    st.header("Underwater Plot (Duration of Pain)")
    
    # Create the underwater plot as a shaded area chart
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
    st.plotly_chart(fig_underwater, use_container_width=True)

with col2:
    st.header("Drawdown Plot (Magnitude of Pain)")

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

    # Add annotations for the top drawdowns
    for i, row in top_drawdowns.head(1).iterrows(): # Annotate only the worst one to keep it clean
        fig_drawdown.add_annotation(
            x=row['Trough Date'], y=float(row['Max Drawdown %'].strip('%')),
            text=f"Worst DD: {row['Max Drawdown %']}",
            showarrow=True, arrowhead=2, arrowcolor="red",
            ax=-40, ay=-40,
            bgcolor="white"
        )

    fig_drawdown.update_layout(yaxis_title="Drawdown from Peak (%)", yaxis_ticksuffix="%")
    st.plotly_chart(fig_drawdown, use_container_width=True)

# --- Detailed Analysis Table ---

st.header("Top 5 Drawdown Periods")
st.markdown("This table provides context for the charts above, detailing the worst drawdown events.")
st.dataframe(top_drawdowns, use_container_width=True, hide_index=True)