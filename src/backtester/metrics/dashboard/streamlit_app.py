import streamlit as st

overview = st.Page("pages/overview.py", title="Overview")
perf = st.Page("pages/performance_analysis.py", title="Performance Analysis")
risk = st.Page("pages/risk_analysis.py", title="Risk Analysis")
trade = st.Page("pages/trade_analysis.py", title="Trade Analysis")

pp = st.navigation([overview, perf, risk, trade])

pp.run()