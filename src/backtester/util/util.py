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

def str_to_pandas(interval): # 1m, 2m, 5m, 15m, 30m, 60m, 90m, 1h, 1d, 5d, 1wk, 1mo, 3mo
    if "m" in interval:
        return interval.replace("m", "min")
    elif "d" in interval:
        return interval.replace("d", "D")
    return interval
