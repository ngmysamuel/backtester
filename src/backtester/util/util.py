from typing import NamedTuple  # identical to collections.namedtuple
import datetime

class BarTuple(NamedTuple):
    Index: datetime.datetime
    open: float
    high: float
    low: float
    close: float
    volume: int
    raw_volume: int

def str_to_seconds(interval):
    match interval:
        case "1m":
            return 60
        case "2m":
            return 120
        case "3m":
            return 180
        case "5m":
            return 300
        case "10m":
            return 600
        case "15m":
            return 900
        case "30m":
            return 1800
        case "60m" | "1h":
            return 3600
        case "90m":
            return 5400
        case "1d":
            return 86400
        case _:
            raise ValueError(f"{interval} is not supported")


def str_to_pandas(interval):
    """
    Used to convert the interval-strings used in Yahoo to those used in Pandas
    Yahoo: 1m, 2m, 5m, 15m, 30m, 60m, 90m, 1h, 1d, 5d, 1wk, 1mo, 3mo
    Pandas: https://pandas.pydata.org/pandas-docs/stable/user_guide/timeseries.html#dateoffset-objects
    """
    if "m" in interval:
        return interval.replace("m", "min")
    elif "d" in interval:
        return interval.replace("d", "B")
    return interval
