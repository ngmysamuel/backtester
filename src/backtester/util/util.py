def str_to_seconds(interval):
    match interval:
        case "1m":
            return 60
        case "2m":
            return 120
        case "3m":
            return 180
        case "5m":
            return 500
        case "15m":
            return 900
        case "1d":
            return 86400
        case _:
            raise ValueError(f"{interval} is not supported")
