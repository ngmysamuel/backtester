import redis
import json
import os
from backtester.cli import run 
import time
from backtester.enums.st_session_status import ST_SESSION_STATUS
from backtester.enums.st_job_status import ST_JOB_STATUS
import traceback

# Connect to Redis
r = redis.Redis(host=os.getenv('REDIS_HOST', 'localhost'), port=6379, db=0, decode_responses=True)

def start_worker():
    print("Worker Listening for jobs...")
    while True:
        # blpop blocks until an item is available (0 = infinite timeout)
        _, message = r.blpop('job_queue', 0)
        job_data = json.loads(message)
        job_id = job_data['job_id']
        session_id = job_data['session_id']
        params = job_data['params']
        
        # Notify "Processing"
        r.set(f"job:{job_id}:status", ST_JOB_STATUS.RUNNING.value)
        r.set(f"{session_id}:status", ST_SESSION_STATUS.IN_PROGRESS.value)
        
        try:
            run(
                output_path=params["output_path"],
                ticker_list=params["ticker_list"],
                benchmark=params["benchmark"],
                strategy=params["strategy"],
                position_calc=params["position_calc"],
                slippage=params["slippage"],
                initial_capital=params["initial_capital"],
                start_date=params["start_date"],
                end_date=params["end_date"]
            )
            
            r.set(f"job:{job_id}:status", ST_JOB_STATUS.DONE.value)
            r.set(f"{session_id}:status", ST_SESSION_STATUS.AWAITING.value)
            
        except Exception as e:
            traceback.print_exc()
            r.set(f"job:{job_id}:status", ST_JOB_STATUS.ERROR.value)

if __name__ == "__main__":
    start_worker()