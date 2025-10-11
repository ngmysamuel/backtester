import streamlit as st
import sys

def main(arg=None):
  overview = st.Page("pages/overview.py", title="Overview")
  perf = st.Page("pages/performance_analysis.py", title="Performance Analysis")
  risk = st.Page("pages/risk_analysis.py", title="Risk Analysis")
  trade = st.Page("pages/trade_analysis.py", title="Trade Analysis")

  pp = st.navigation([overview, perf, risk, trade])
  st.session_state.arguments = arg

  pp.run()

if __name__ == "__main__":
  if len(sys.argv) > 1:
    a2 = [a.replace(" -- --", "") for a in sys.argv[1:]]
    args = {arg.split(" ")[0]: arg.split(" ")[1] for arg in a2}
    main(args)
  else:
    main()