# Backtester

### Dependencies
1. Poetry

### Run
```
git clone https://github.com/ngmysamuel/backtester.git
cd backtester
poetry install
poetry run backtester run
```

### Test
```
poetry run pytest
```

### Pulling CSV data
```
import yfinance as yf
dat = yf.Ticker("MSFT")
df = dat.history(period='5y') # period must be one of: 1d, 5d, 1mo, 3mo, 6mo, 1y, 2y, 5y, 10y, ytd, max
df.to_csv("MSFT.csv")
```