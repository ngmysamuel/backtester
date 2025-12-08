# Backtester

<h3 align="center"> ⚠ Work in progress ⚠</h3>
<p align="center"> You might notice some formatting issues / lack of documentation in the meantime.</p>

### Prerequisites
1. Poetry

### Run
Trigger a backtest
```
git clone https://github.com/ngmysamuel/backtester.git
cd backtester
poetry install
poetry run backtester run --data-dir path\to\data_dir\ --strategy moving_average --exception-contd 1
```
There are 6 parameters
1. data-dir
    - The path to the directory where the CSVs of OHLC data of the tickers you specified in config.yaml
    - Necessary if data-source is csv
    - Default is None
2. data-source
    - Available options are in config.yaml under "data_handler"
    - Default is "yf"
3. position_calc
    - Method used to calculate the position size of each trade
    - Available options are in config.yaml under "position_sizer"
    - Default is "atr"
4. slippage
    - Available options are in config.yaml under "slippage"
    - Default is "multi_factor_slippage"
5. strategy
    - Available options are in config.yaml under "strategies"
    - Default is "buy_and_hold_simple"
6. exception-contd
    - either 1 or 0
    - indicates whether to continue the backtest if portfolio cash balance drops below 0
    - Default is 1

### Dashboard
Run this to view and interact with the data generated from a backtest. You must have ran a backtest at least once.
```
poetry run backtester dashboard
```

### Test
Run the testcases
```
poetry run pytest
```
For a specific file
```
poetry run pytest tests\execution\test_simulated_execution_handler.py
```

### Pulling CSV data
Identical to using data-source = "yf"
```
import yfinance as yf
dat = yf.Ticker("MSFT")
df = dat.history(period='5y') # period must be one of: 1d, 5d, 1mo, 3mo, 6mo, 1y, 2y, 5y, 10y, ytd, max
df.to_csv("MSFT.csv")
```

### Important Caveats
1. Slippage Model 
    - The multi factor slippage model assumes daily data
    - If you have data of other intervals, you must update the parameters used by it in config.yaml
    - If you do not wish the hassle, use the NoSlippage model
    - Note backtester_settings.interval config as well

### Implementation Details
1. Portfolio
    1. Value of positions are calculated using the closing price of each interval. 
    2. Total portfolio value is calculated as the sum of the useable cash, value of positions (shorts are considered negative), and margin locked up
    3. Cash shown is useable cash i.e. not locked up as margin
    4. Initial trade size is defined by backtester_settings.initial_position_size
2. Shorting
    1. Short sold position in a stock is possible but many assumptions are made. You can borrow the shares indefinitely. 
    2. Borrow costs and margin are calculated at the end of the trading day
    3. Required margin is immediately deducted from the useable cash balance
    4. If there is a negative cash balance at the start of a bar, an exception is raised (pass continue=1 to continue)
3. Simulated Execution
    1. Market Orders are filled at open i.e. at the opening price of the next interval from the order placed. Market On Close are filled at close when the current interval of market data is the last slice of the day.
    2. All orders are filled entirely i.e. no partial filling
4. Data Handling (Live)
    1. Consolidates all ticks within interval timespan (backtester_settings.interval) into a single bar of high, low, open, and close.
    2. Stop when the time spent listening for messages exceeds the period (backtester_settings.period)
    3. For short periods, use the buy_and_hold_simple strategy to ensure the tearsheet generation works (there will be no buy signals generated using moving_average strategy as the time span of its windows are too long)
5. Volume (Live)
    - Note that live data from yfinance doesn't seem to have clean volume information i.e. it is not monotonically increasing. This is handled by:
        - 2 dictionaries capturing the volumes on a day basis and an interval basis
        - The day basis dictionary updates at the end of every interval.
            - It is incremented by the interval basis value at the end of every interval. It is reset to zero at the end of the trading day
        - The interval basis dictionary updates on every message
            - It takes the message volume and subtracts the volume in the day basis dictionary to get the current interval's volume.
            - If the result is smaller than the previous interval value, it is ignored
            - It is reset to 0 at the end of every interval
6. Position Sizing (General)
    1. return None if there is not enough data to generate a value. This will cause the portfolio module to reuse the last used position size
    2. if it is the first trade, it will be backtester_settings.initial_position_size in config.yaml
7. Position Sizing (ATR)
    1. Implemented as part of the position sizer module with attributes defined in config.yaml
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
8. Metrics
    1. Quantstats
        1. https://github.com/ranaroussi/quantstats/blob/main/quantstats/reports.py
        2. https://github.com/ranaroussi/quantstats/blob/main/quantstats/stats.py
    2. Streamlit
    3. Note that there are differnces in the values you see in the tearsheet versus what I've calculated and presented via Steamlit
        1. For example, Quantstats starts their calculation from the first date where there is a non-zero return. Refer to _match_dates() in reports.py. For e.g. CAGR is 1.6% if we go by the full time span while Quanstats, relying on a smaller time period, returns a larger CAGR - 1.9%
        2. Another example, Longest Drawdown Duration is present by Quantstats as the number of days from start to end while I present the number of trading intervals
9. Annulization of Sharpe
    1. The factor depends on what kind of time period we are calculating Sharpe over which in turn depends on the data interval we are using. If the data interval is daily, the Sharpe Ratio is daily. To get the sharpe ratio for the year, we need to "increase" the ratio to a year's basis. There are 252 trading days in a year which means the annualization factor is 252.
    2. Uses the the interval stated in config.yaml
    3. If its daily, annualization factor is 252. If its minutely, 98280. See get_annualization_factor() in _util.py
10. Transaction Cost Modelling
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
            - Randome Noise - modelled with a normal distribution; no model is perfect
            - Slippage - (Spread Cost) + (Market Impact) + (Momentum Cost*Liquidity Cost) + (Random Noise)
    3. Links
        - Educational: https://www.quantstart.com/articles/Successful-Backtesting-of-Algorithmic-Trading-Strategies-Part-II/
        - Understanding Almgren et al.: https://quant.stackexchange.com/a/55897
        - Almgren et al.: https://www.cis.upenn.edu/~mkearns/finread/costestim.pdf
        - An approach: https://www.stephendiehl.com/posts/slippage/
        - Heavily adapted from: https://github.com/QuantJourneyOrg/qj_public_code/blob/main/slippage-analysis.py
        - Explanations: https://quantjourney.substack.com/p/slippage-a-comprehensive-analysis
11. One way negative cash arises because we use market orders - we might have position sized to use up all remaining cash based on the ATR of the ticker. But on the next open, price rockets and the order fulfilled for a value more than what cash is available.

### To Do
- Slippage model  - supporting other time periods automatically 
    - switches variables to use when the trading interval changes. The slippage model only supports daily data now e.g. 252 trading periods in a year. The trading interval would be the variable in config.yaml
    - Intraday data support
- Polish the entry point of application, cli.py
- Test cases for multi factor slippage modelling
- Add explanation for how create own implementation of various items e.g. position sizer, slippage model, etc
- Logger
- Other order types e.g. Limit order
- Modelling probability of fill for limit orders
- Use the decimal library instead of float types
- An integrated test across different data source modes, comparing the output csv with a reference csv
- Warm up historical data for calculations like ATR position sizing
    - another config parameter that contains the names of all the window parameters
    - For historical CSV, check if there exists a data point that is the max of all those window parameters behind
    - For live, check if the data dir is give. If so, look for a data point that is the max of all those window parameters behind
    - If at any point, there isn't, send a warning
- Handling web socket failure - auto reconnect

### Notes

Periods for pandas: https://pandas.pydata.org/docs/reference/api/pandas.Period.asfreq.html

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