# Backtester

<h3 align="center"> ⚠ Work in progress ⚠</h3>
<p align="center"> You might notice some formatting issues / lack of documentation in the meantime.</p>

# How to run
## Docker
### Prerequisites
1. Docker
### Notes
For the full control over the options, run using the script method (see below)
### Steps
Visit localhost:8501 after spinning up the containers
```
git clone https://github.com/ngmysamuel/backtester.git
cd backtester
docker compose up
```
Misc
```
docker images
docker rmi -f <image_id>
docker volume ls
docker volume rm <volume_name>
docker compose up --build --force-recreate
docker compose up --build --force-recreate
docker system df
```
Check redis
```
docker exec -it <container_id> redis-cli
KEYS '*'
```
Powershell
```
Test-NetConnection -ComputerName 34.133.45.165 -Port 8501
ssh -i <private_key> <username>@34.133.45.165
```
Linux
```
sudo systemctl restart ssh
```


## Script
### Prerequisites
1. Poetry
### Notes
More effort than via Docker but has the most options
### Triggering a backtest
```
git clone https://github.com/ngmysamuel/backtester.git
cd backtester
poetry install
poetry run backtester run --strategy moving_average
```
There are 6 parameters
1. data-dir
    - The path to the directory where the CSVs of OHLC data of the tickers you specified in config.yaml
    - Necessary if data-source is csv
    - Default is None
2. data-source
    - Available options are in config.yaml under "data_handler"
    - Default is "yf"
3. position-calc
    - Method used to calculate the position size of each trade
    - Available options are in config.yaml under "position_sizer"
    - Default is "atr"
4. slippage
    - Available options are in config.yaml under "slippage"
    - Default is "multi_factor_slippage"
5. strategy
    - Available options are in config.yaml under "strategies"
    - Default is "moving_average"
6. to-analyze-sentiment
    - --analyze-sentiment for True
    - --no-analyze_sentiment for False
    - Only works if data-source = live
    - Default is False

### Visualizing a backtest
Run this to view and interact with the data generated from a backtest. You must have ran a backtest at least once.
```
poetry run backtester dashboard
```

# Testing
Run the all testcases (including integration tests)
```
poetry run pytest
```
For only unit tests
```
poetry run pytest -m "not integration"
```
For a specific file
```
poetry run pytest tests\execution\test_simulated_execution_handler.py
```
For all integration tests. Tests requiring internet access are labelled "live_integration"
```
poetry run pytest -m "integration"
```
Static type checking
```
poetry run mypy src\backtester\util\bar_aggregator.py
```

# Pulling CSV data
Identical to using data-source = "yf"
```
import yfinance as yf
dat = yf.download("msft", start="2025-11-24", end="2025-11-29", interval="1m",multi_level_index=False,ignore_tz=True)
dat.to_csv("MSFT_1m.csv")
```

# Important Notes
1. Intervals
    - The base interval must be most granular time interval across all strategies, etc.
2. Live Sentiment
    - You need an API key from https://newsapi.org/
    - Store it as an environment variable under the name "NEWS_API"

# Implementation Details
1. Dual Frequency
    1. The backtester runs on a single frequency (the base frequency) and all other frequencies required by the strategies are resampled from it
    2. As a result, the base frequency has to be the most granular
    3. Implemented by the bar_aggregator and bar_manager classes which interacts with the rest of the system with the on_interval method
    4. Classes which require this information must implement the OnIntervalProtocol - the subscription method of the bar_manager only accepts classes which implements the protocol 
2. Portfolio
    1. Value of positions are calculated using the closing price of each interval. 
    2. Total portfolio value is calculated as the sum of the useable cash, value of positions (shorts are considered negative), and margin locked up
    3. Cash shown is useable cash i.e. not locked up as margin
    4. Initial trade size is defined by backtester_settings.initial_position_size
    5. Short sold instruments are a negative to your total portfolio value - they are a liability that you must pay back eventually
    6. How does a short sell impacts the portfolio's cash and total?
        - Say, you have 1 AAPL stock, $0 cash, 50% margin maintenance
        - You sell 2 AAPL stock at $10 each
        - You now have $20 cash BUT -$10 equity as the short sold instrument is considered a liability on your equity
        - Hence, portfolio equity is $10
        - And because of the maintenance margin of 1.5x, which works out to $15 having to be kept as margin
        - Hence, cash is $5
3. Strategies
    1. Returns the Target Holding, not the trade delta. For Target Holding Size, see Position Sizer
    2. Signals only bullish / bearish
    3. Practically stateless
4. Risk Manager (Simple)
    1. The final hurdle before an order is sent into the queue
    2. Across 6 metrics
        - Max Order Quantity
            - A hard limit on the number of shares/contracts per single order.
            - Set -1 to skip this check.
        - Max Notional Value
            - A limit on the dollar value of a single order.
            - Set -1 to skip this check.
        - Max Daily Drawdown
            - If the strategy has lost more than X% since the market opened today, it is forbidden from opening new positions. It can only issue "Close" orders to reduce risk.
        - Gross Exposure Limit
            - Set -1 to skip this check.
        - Net Exposure Limit
            - Set -1 to skip this check.
        - Percent of Volume (POV) Check
            - Large orders move the market (slippage). You cannot buy 10,000 shares if only 500 traded in the last minute.
        - Order Rate Limits (Messages Per Second)
            - Limit the number of orders sent within a rolling time window
5. Quantity
    1. The quantity in an OrderEvent is always positive, the direction of the order is given in the direction attribute
    2. The quantity in the current_holdings attribute of the portfolio module has polarity, indicating if it is in a short sold position
6. Shorting
    1. Short sold position in a stock is possible but many assumptions are made. You can borrow the shares indefinitely. 
    2. Borrow costs and margin are calculated at the end of the trading day
    3. Required margin is immediately deducted from the useable cash balance
    4. If there is a negative cash balance at the start of a bar, an exception is raised (pass continue=1 to continue)
7. Simulated Execution
    1. Market Orders are filled at open i.e. at the opening price of the next interval from the order placed. Market On Close are filled at close when the current interval of market data is the last slice of the day.
    2. All orders are filled entirely i.e. no partial filling
6. Data Handling (Live)
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
    1. At any given moment, how much exposure to the market should I have? That is, the Market Risk and not Liquidity Risk (which might be handled instead with a dedicated Time-Weighted Average Price executor)
    2. Works with the strategy. Say the strategy is bearish on a stock. This position sizer will say how much exposure we want to that stategy's signal, say risking 50 shares is ok. I own 100 shares at the moment. Selling the 100 shares reduces market risk as they are off the market, it only expriences liquidity risk. But I still want exposure to the 50 shares as stated by the position sizer. So another 50 is sold. 
    1. return None if there is not enough data to generate a value. This will cause the portfolio module to reuse the last used position size
    2. if it is the first trade, it will be backtester_settings.initial_position_size in config.yaml
7. Position Sizing (ATR)
    1. Implemented as part of the position sizer module with attributes defined in config.yaml
    2. Calculates the share count such that some multipler of the securiy' ATR move against the position results in a loss of exactly X% of the portfolio equity.
    2. Calculated at the end of the interval, before new bars are added
    4. stop_loss_distance = atr * atr_multiplier where if the price moves 2x the ATR, and we stop loss, we at most loss capital_to_risk
    3. position_size = capital_to_risk / stop_loss_distance where
    4. position_size = number of stocks to buy, rounded to the decimal you have specified in config.yaml
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
            - Does not assume continuously observed prices. For example, on daily data (low frequency), the "fundamental volatility" (the trend) usually drowns out the "microstructure noise" (the spread), causing other estimators to be heavily biased or return zeros.
            Thus unlike the previous estimators, this results in a more accurate spread without the downward bias
            - By making use of various combinations of OHLC prices (across time, if high equals open, etc), 4 estimators can be derived which the paper calls Discrete Generalized Estimators. These 4 estimators work best in different market conditions; some being more accurate in volatile situations for example. The paper blends them together, weighting them accordingly to achieve a final estimator that has the smallest estimation variance under any scenario
            - EDGE, as a result, is a robust and more accurate estimator which can be applied to a wide range of frequencies (albeit it is mentioned that higher frequency data is better) 
        3. Volume Metrics
            - Moving average of volume over several window sizes 
            - Ratio of today's volume vs the average
            - Volume Surge - indicator of outliers in volume, clipped to a max of 5
        4. Composite Metrics
            - Amihud Illiquidity - a look at the product's inherent illiquidity. Price movement per dollar traded
            - Turnover (Coeff of Variance) - standardised metric to compare volatility across products (e.g. capitalization)
            - Volatility Cost - a cost amplifier for the other factors
            - Price acceleration - quantifies market sentiment, if it increases it means that a stampede is forming.
            - Momentum Cost - the cost incurred when other traders are trying to make the same move as you. If moving with market (taking liquidity), slippage is more. If moving against the market (increasing liquidity), slippage is less.
            - Liquidity Cost - distinguishes between different types of assets e.g. blue chips vs unknown penny stocks
        5. Combining the above
            - Participation rate - ratio of the current trade to the volume on that day
            - Market Impact - quanitifies the adverse price movement caused directly by the pressure of our own order. Scales along a concave relation (empircallly set to the 3/5 power relationship); doubling trade size does not double cost, it would be less than that. Normalized by the average volume in the medium term with a dampener provided by a negative exponential of the coefficient of variation
            - Random Noise - modelled with a lognormal distribution and applied multiplicatively on final slippage - no model is perfect
            - Slippage - (Spread Cost) + (Market Impact) + (Momentum Cost*Liquidity Cost) + (Random Noise)
    3. Links
        - Educational: https://www.quantstart.com/articles/Successful-Backtesting-of-Algorithmic-Trading-Strategies-Part-II/
        - Understanding Almgren et al.: https://quant.stackexchange.com/a/55897
        - Almgren et al.: https://www.cis.upenn.edu/~mkearns/finread/costestim.pdf
        - An approach: https://www.stephendiehl.com/posts/slippage/
        - Heavily adapted from: https://github.com/QuantJourneyOrg/qj_public_code/blob/main/slippage-analysis.py
        - Explanations: https://quantjourney.substack.com/p/slippage-a-comprehensive-analysis
11. One way negative cash arises because we use market orders - we might have position sized to use up all remaining cash based on the ATR of the ticker. But on the next open, price rockets and the order fulfilled for a value more than what cash is available.
12. Issue: if there are no messages while using the live data handler, an exception will be thrown in data_aggregator.py
    - Fix: 
        - check in bar_aggregator.py on_heartbeat() if the return of get_latest_bars() is empty or not before indexing on it
    - Consideration: 
        - this case would only happen when using the live data handler and since the start of the backtest there has been no data coming in
        - initially considered handling it in the data handler classes where we would skip sending out the MarketEvent if there is no previous bar data at all
        - However, did not feel right to handle it in the data handler method. Since there can multiple tickers and suppose only one ticker has data. We should still push a market event to ensure that that one ticker is not short changed. But remember that market event has NO ticker information. The bar manager will have every bar aggregator check get the new records. It might succeed with the one ticker that has data but it will still fail on all the tickers that had no data. 
        - Hence, it would better to handle it in the data aggregator method (line 26)
13. Issue: if there are two signal events before their corresponding fill event, you run the risk of negative cash.
    - Fix: 
        - reserve cash in the portfolio for each order and unreserve it when the fill comes in
    - Considerations:
        - Order Event
            - Each order has an ID
            - Store it in a dict (id: order estimated cost) in the portfolio 
        - Execution Handler
            - It creates the Fill Event with a parameter pointing to the order ID
        - Portfolio
            - In the on fill method, lookup the dict for that order using the order id in the fill event. Remove it if entirely filled or reduce it if partial fill
            - If the total fill cost is more than the estimated cost in the order, just remove the order from the dict
        - On signal
            - Total cash minus sum of the estimate pot = new usable cash 
        - Not possible to have the estimated cost as one pot. If the actual fill cost is more than the estimate, you are reducing the estimate pot by more than it should be. See example below 
            - Start out with InFlight -> 5 7, Cash -> 10, 
            - Fill quantity -> 6
            - It should become InFlight: 7, Cash: 4
        - We could instead keep the estimated cost in the order event, have the fill event copy it. And in the on fill method, subtract the estimated cost from the estimate pot. But I think we keep responsibilities separate, no need to pass information everywhere. 


# To Do
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
- Warm up historical data for calculations like ATR position sizing
    - another config parameter that contains the names of all the window parameters
    - For historical CSV, check if there exists a data point that is the max of all those window parameters behind
    - For live, check if the data dir is give. If so, look for a data point that is the max of all those window parameters behind
    - If at any point, there isn't, send a warning
- Handling web socket failure - auto reconnect
- Multi strategy backtesting
- Update all files to pass static type checking
- Portfolio auto rebal
- Look through commissions calculations again
- AS-IS time interval for live data - when a tick comes in, push it out immediately
- use pytest.approx for float assertions
- update test cases
- to switch from yf websocket to alpaca websocket - yf websockets have no vol data for SPY
- to build historical sentiment reader

# Notes

Periods for pandas: https://pandas.pydata.org/docs/reference/api/pandas.Period.asfreq.html

An event driven backtester is a pure chronological construct unlike a vectorized backtester which has the prices at all time periods already.

### Look Ahead Bias 
1. Incorporating future data releases (corporate and economic)  
A strategy that relies on fundamental information to derive ideal price might use a future corporate release to calculate that ideal price and finds the prices BEFORE the corporate release to be ideal. But this is an unfair advantage.
2. Using future-adjusted prices  
A strategy that buys a stock if it falls below $55. The stock currently trades between $90 and $100. A 2-for-1 stock split in the future and having a retroactive price adjustment means the stock price in the past will be $48 for example. Making it a BUY signal where no BUY signal would have been generated if an unadjusted price was used.  
When a company pays a dividend, its stock price typically drops by the dividend amount on the ex-dividend date. Adjusted price data removes this drop, making the price series smooth. 
If a strategy depends on detecting sudden price drops (e.g., a "buy the dip" strategy), using adjusted prices would remove these drops from the historical data, causing the backtest to miss valid trading signals. 
3. Using next-bar data  
A strategy that buys a stock if the closing price is higher than the opening price. On Monday morning, the backtest looks at Monday's historical data, sees that the closing price was indeed higher than the opening price, and records a profitable trade. 

### Numpy and Pandas
1. Standard Deviation
    1. Numpy assumes population level s.d. (ddof = 0) while pandas assumes sample (ddof = 1)