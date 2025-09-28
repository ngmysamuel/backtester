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

### Implementation Details
1. Portfolio
    1. Value of positions are calculated using the closing price of each interval. 
    2. Total portfolio value is calculated as the sum of the useable cash, value of positions (shorts are considered negative), and margin locked up
    3. Cash shown is useable cash i.e. not locked up as margin
2. Shorting
    1. Short sold position in a stock is possible but many assumptions are made. You can borrow the shares indefinitely. 
    2. Borrow costs and margin are calculated at the end of the trading day
    3. Required margin is immediately deducted from the useable cash balance
    4. If there is a negative cash balance at the start of a bar, an exception is raised (pass continue=1 to continue)
3. Simulated Execution
    1. Market Orders are filled at open i.e. at the opening price of the next interval from the order placed. Market On Close are filled at close when the current interval of market data is the last slice of the day.
    2. All orders are filled entirely i.e. no partial filling
4. Position Sizing
    1. Implemented in the portfolio module with attributes defined in config.yaml
    2. position_size = capital_to_risk // (atr * atr_multiplier) where
    3. position_size = number of stocks to buy
    4. captial_to_risk = risk_per_trade * total_portfolio_value where
        1. risk_per_trade = a percent that you are willing lose in a single trade
    5. atr = average true range where
        1. Wilder's Smoothing Method
        2. initialization is handled with a simple average of the true range over the number of periods


### Notes

An event driven backtester is a pure chronological construct unlike a vectorized backtester which has the prices at all time periods already.

#### Look Ahead Bias 
1. Incorporating future data releases (corporate and economic)  
A strategy that relies on fundamental information to derive ideal price might use a future corporate release to calculate that ideal price and finds the prices BEFORE the corporate release to be ideal. But this is an unfair advantage.
2. Using future-adjusted prices  
A strategy that buys a stock if it falls below $55. The stock currently trades between $90 and $100. A 2-for-1 stock split in the future and having a retroactive price adjustment means the stock price in the past will be $48 for example. Making it a BUY signal where no BUY signal would have been generated if an unadjusted price was used.  
When a company pays a dividend, its stock price typically drops by the dividend amount on the ex-dividend date. Adjusted price data removes this drop, making the price series smooth. 
If a strategy depends on detecting sudden price drops (e.g., a "buy the dip" strategy), using adjusted prices would remove these drops from the historical data, causing the backtest to miss valid trading signals. 
3. Using next-bar data  
A strategy that buys a stock if the closing price is higher than the opening price. On Monday morning, the backtest looks at Monday's historical data, sees that the closing price was indeed higher than the opening price, and records a profitable trade. 