from enum import Enum

class ST_JOB_STATUS(Enum):
  PENDING = "Pending Job Start"
  DONE = "Done"
  SUBMITTED = "Submitted"
  RUNNING = "Running"
  ERROR = "Error"