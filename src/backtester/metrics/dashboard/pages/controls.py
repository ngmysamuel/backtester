import datetime
import json
import os
import time
import uuid
from pathlib import Path

import pandas as pd
import redis
import streamlit as st

from backtester.enums.st_job_status import ST_JOB_STATUS
from backtester.enums.st_session_status import ST_SESSION_STATUS

r = redis.Redis(host=os.getenv('REDIS_HOST', 'localhost'), port=6379, db=0, decode_responses=True)
if "session_id" not in st.session_state:
    st.session_state["session_id"] = str(uuid.uuid4())
if "job_id" not in st.session_state:
    st.session_state["job_id"] = -1
if "to_poll" not in st.session_state:
    st.session_state["to_poll"] = False
if "path_prefix" not in st.session_state:
    st.session_state["path_prefix"] = "/output/"

st.title("Quant Execution Dashboard")

session_status = r.get(f"{st.session_state["session_id"]}:status") or ST_SESSION_STATUS.AWAITING.value
job_status = r.get(f"job:{st.session_state["job_id"]}:status") or ST_JOB_STATUS.PENDING.value

col1, col2 = st.columns(2)
col3, col4 = st.columns(2)
with col1: 
    st.write(f"Session ID: {st.session_state["session_id"]}")
with col2:
    session_status_box = st.empty()
    session_status_box.write(f"Session Status: {session_status}")
with col3:
    job_id_box = st.empty()
    job_id_box.write(f"Job ID: {st.session_state["job_id"]}")
with col4:
    job_status_box = st.empty()
    job_status_box.write(f"Job Status: {job_status}")

# 1. Configuration Section
tickers = st.text_input("Tickers", "MSFT", help="Comma delimited list of tickers to backtest")
benchmark = st.text_input("Benchmark", "SPY", help="Benchmark - only 1 ticker")
strategy = st.selectbox("Select Strategy", ["moving_average", "buy_and_hold_simple"])
position_calc = st.selectbox("Select Position Sizer", ["atr", "no_position_sizer"])
slippage = st.selectbox("Select Position Sizer", ["multi_factor_slippage", "no_slippage"])
start_date = st.date_input("Start of backtest period", datetime.date(2020, 9, 15))
end_date = st.date_input("Start of backtest period", datetime.date(2025, 12, 12))
capital = st.number_input("Initial Capital", value=100000)

to_disable = job_status in [ST_JOB_STATUS.RUNNING.value, ST_JOB_STATUS.SUBMITTED.value]
if st.button("Run Backtest", disabled=to_disable):
    # Generate ID and push to Redis
    job_id = str(uuid.uuid4())
    job_id_box.write(f"Job ID: {job_id}")
    st.session_state['job_id'] = job_id

    output_path = f"{st.session_state["path_prefix"]}{st.session_state["session_id"]}/{job_id}/"
    nested_directory_path = Path(output_path)
    nested_directory_path.mkdir(parents=True, exist_ok=True)

    ticker_list = tickers.split(",")
    if "," in benchmark:
        benchmark = benchmark.split(",")[0]

    job_payload = {
        "job_id": job_id,
        "session_id": st.session_state["session_id"],
        "params": {
            "ticker_list": ticker_list,
            "benchmark": benchmark,
            "strategy": strategy,
            "position_calc": position_calc,
            "slippage": slippage,
            "initial_capital": capital, 
            "start_date": start_date.strftime("%d/%m/%Y 00:00:00"),
            "end_date": end_date.strftime("%d/%m/%Y 00:00:00"),
            "output_path": output_path
        }
    }
    r.rpush('job_queue', json.dumps(job_payload))
    
    # Store ID in session to track it
    r.set(f"{st.session_state["session_id"]}:status", ST_SESSION_STATUS.IN_PROGRESS.value)
    r.set(f"job:{st.session_state["job_id"]}:status", ST_JOB_STATUS.SUBMITTED.value)
    session_status = ST_SESSION_STATUS.IN_PROGRESS.value
    job_status = ST_JOB_STATUS.SUBMITTED.value
    st.session_state["to_poll"] = True

# 2. Polling Section
if st.session_state["to_poll"]:
    job_id = st.session_state['job_id']

    if job_status not in [ST_JOB_STATUS.DONE.value, ST_JOB_STATUS.ERROR.value]:
        # Force a reload to poll again in a second
        time.sleep(1)
        st.rerun()
    elif job_status == ST_JOB_STATUS.DONE.value:
        st.toast("Backend complete", icon="ℹ")
        output_file = f"{st.session_state["path_prefix"]}{st.session_state["session_id"]}/{job_id}/equity_curve.csv"
        if os.path.exists(output_file):
            st.toast("Backtest Successful!", icon="🎉")
        df = pd.read_csv(f"{st.session_state["path_prefix"]}{st.session_state["session_id"]}/{job_id}/equity_curve.csv")
        df["timestamp"] = pd.to_datetime(df["timestamp"])
        df = df.set_index("timestamp")
        st.session_state.df = df
        st.session_state["to_poll"] = False
    elif job_status == ST_JOB_STATUS.ERROR.value:
        r.set(f"{st.session_state["session_id"]}:status", ST_SESSION_STATUS.AWAITING.value)
        session_status = ST_SESSION_STATUS.AWAITING.value
        st.session_state["to_poll"] = False