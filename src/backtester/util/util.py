import datetime
import re
from typing import NamedTuple, Optional, TypedDict  # identical to collections.namedtuple


class BarDict(TypedDict):
    Index: datetime.datetime
    open: float
    high: float
    low: float
    close: float
    volume: int
    raw_volume: Optional[int] 

class BarTuple(NamedTuple):
    Index: datetime.datetime
    open: float
    high: float
    low: float
    close: float
    volume: int
    raw_volume: Optional[int]


MONTHS_IN_YEAR = 12.0
DAYS_IN_YEAR = 365.0
MINUTES_IN_HOUR = 60.0
TRD_HOURS_IN_DAY = 6.5
TRD_DAYS_IN_YEAR = 252.0
STRING_TO_RESAMPLE_WINDOW = {
    "Weekly": "W",
    "Monthly": "ME",
    "Quaterly": "QE",
    "Yearly": "YE",
}


def get_annualization_factor(interval: str) -> float:
    """
    Calculates the annualization factor based on the data's frequency,
    1m, 2m, 5m, 15m, 30m, 60m, 90m, 1h, 1d, 5d, 1wk, 1mo, 3mo (to create enum)
    Able to handle generic interval strings (e.g., "1m", "4h", "1d") to calculate
    annualization factors dynamically but stick to the well established ones to
    be sure
    """
    # separate numbers from letters (e.g., "15m" -> ["15", "m"])
    match = re.match(r"([0-9]+)([a-zA-Z]+)", interval)
    if not match:
        raise ValueError(f"Invalid interval format: {interval}")

    value = int(match.group(1))
    unit = match.group(2).lower()  # Normalize to lowercase

    if unit == "m" or unit == "min":
        # (Minutes per day * Trading days) / interval_value
        return (TRD_HOURS_IN_DAY * 60 * TRD_DAYS_IN_YEAR) / value

    elif unit == "h":
        # (Hours per day * Trading days) / interval_value
        return (TRD_HOURS_IN_DAY * TRD_DAYS_IN_YEAR) / value

    elif unit == "d":
        return TRD_DAYS_IN_YEAR / value

    elif unit == "w" or unit == "wk":
        return 52.0 / value

    elif unit == "mo":
        return MONTHS_IN_YEAR / value

    else:
        raise ValueError(f"Unsupported time unit: {unit}")


def str_to_seconds(interval: str) -> int:
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


def str_to_pandas(interval: str) -> str:
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
