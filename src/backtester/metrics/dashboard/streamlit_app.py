import streamlit as st
import sys

def main(arg=None):
  if arg and "is_docker" in arg and int(arg["is_docker"]):
    controls = st.Page("pages/controls.py", title="Controls")
  overview = st.Page("pages/overview.py", title="Overview")
  perf = st.Page("pages/performance_analysis.py", title="Performance Analysis")
  risk = st.Page("pages/risk_analysis.py", title="Risk Analysis")
  trade = st.Page("pages/trade_analysis.py", title="Trade Analysis")

  if arg and "is_docker" in arg and int(arg["is_docker"]):
    pp = st.navigation([controls, overview, perf, risk, trade])
  else:
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