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

### Dashboard
```
poetry run backtester dashboard
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
    2. Calculated at the end of the interval, before new bars are added
    3. position_size = capital_to_risk // (atr * atr_multiplier) where
    4. position_size = number of stocks to buy
    5. captial_to_risk = risk_per_trade * total_portfolio_value where
        1. risk_per_trade = a percent that you are willing lose in a single trade
    6. atr = average true range where
        1. Wilder's Smoothing Method
            1. https://www.macroption.com/atr-calculation/#exponential-moving-average-ema-method
            2. https://www.macroption.com/atr-excel-wilder/
        2. initialization is handled with a simple average of the true range over the number of periods
5. Metrics
    1. Quantstats
        1. https://github.com/ranaroussi/quantstats/blob/main/quantstats/reports.py
        2. https://github.com/ranaroussi/quantstats/blob/main/quantstats/stats.py
    2. Streamlit
    3. Note that there are differnces in the values you see in the tearsheet versus what I've calculated and presented via Steamlit
        1. For example, Quantstats starts their calculation from the first date where there is a non-zero return. Refer to _match_dates() in reports.py. For e.g. CAGR is 1.6% if we go by the full time span while Quanstats, relying on a smaller time period, returns a larger CAGR - 1.9%
        2. Another example, Longest Drawdown Duration is present by Quantstats as the number of days from start to end while I present the number of trading intervals
6. Annulization of Sharpe
    1. The factor depends on what kind of time period we are calculating Sharpe over which in turn depends on the data interval we are using. If the data interval is daily, the Sharpe Ratio is daily. To get the sharpe ratio for the year, we need to "increase" the ratio to a year's basis. There are 252 trading days in a year which means the annualization factor is 252.
    2. Uses the the interval stated in config.yaml
    3. If its daily, annualization factor is 252. If its minutely, 98280. See get_annualization_factor() in _util.py
7. Transaction Cost Modelling
    1. Commisions
    2. Slippage Modelling
        1. Principles
            - a chaotic market means higher slippage
            - going with the market momentum means higher slippage
            - an illiquid instrument means higher slippage
        1. Volatility Metrics
            - Rolling annulized standard deviation based on the close price across several window sizes
        2. Bid Ask Spread
            - Based on Ardia et al. (2024), an efficient estimator (EDGE) described in https://doi.org/10.1016/j.jfineco.2024.103916
            - Does not assume continuously observed prices, unlike previous estimators, resulting in a more accurate spread without the downward bias
            - By making use of various combinations of OHLC prices (across time, if high equals open, etc), 4 estimators can be derived which the paper calls Discrete Generalized Estimators. These 4 estimators work best in different market conditions; some being more accurate in volatile situations for example. The paper blends them together, weighting them accordingly to achieve a final estimator that has the smallest estimation variance under any scenario
            - EDGE, as a result, is a robust and more accurate estimator which can be applied to a wide range of frequencies (albeit it is mentioned that higher frequency data is better) 
        3. Volume Metrics
            - Moving average of volume over several window sizes 
            - Ratio of today's volume vs the average
            - Volume Surge - indicator of outliers in volume, clipped to a max of 5
        4. Composite Metrics
            - Amihud Illiquidity - a look at the product's inherent illiquidity. Price movement per dollar traded
            - Turnover (Coeff of Variance) - standardised metric to compare volatility across products (e.g. capitalization)
            - Price acceleration - quantifies market sentiment, if it increases it means that a stampede is forming. Trading either with or against it is dangerous. 
            - Volatility Cost - a cost amplifier for the other factors
            - Momentum Cost - the cost incurred when other traders are trying to make the same move as you 
            - Liquidity Cost - distinguishes between different types of assets e.g. blue chips vs unknown penny stocks
        5. Combining the above
            - Participation rate - ratio of the current trade to the volume on that day
            - Market Impact - quanitifies the adverse price movement caused directly by the pressure of our own order. Scales along a concave relation (empircallly set to the 3/5 power relationship); doubling trade size does not double cost, it would be less than that. Normalized by the average volume in the medium term with a dampener provided by a negative exponential of the coefficient of variation
            - Slippage - (Spread Cost) + (Market Impact) + (Momentum Cost*Liquidity Cost) + (Random Noise)
    3. Links
        - Educational: https://www.quantstart.com/articles/Successful-Backtesting-of-Algorithmic-Trading-Strategies-Part-II/
        - Understanding Almgren et al.: https://quant.stackexchange.com/a/55897
        - Almgren et al.: https://www.cis.upenn.edu/~mkearns/finread/costestim.pdf
        - An approach: https://www.stephendiehl.com/posts/slippage/
        - Heavily adapted from: https://github.com/QuantJourneyOrg/qj_public_code/blob/main/slippage-analysis.py
        - Explanations: https://quantjourney.substack.com/p/slippage-a-comprehensive-analysis

Periods for pandas: https://pandas.pydata.org/docs/reference/api/pandas.Period.asfreq.html

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

#### Numpy and Pandas
1. Standard Deviation
    1. Numpy assumes population level s.d. (ddof = 0) while pandas assumes sample (ddof = 1)