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
