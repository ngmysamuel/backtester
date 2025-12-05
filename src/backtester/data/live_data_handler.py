from backtester.data.data_handler import DataHandler, BarTuple
import threading
import yfinance as yf
from datetime import datetime
from queue import Queue
import time
import pandas as pd
from backtester.events.market_event import MarketEvent
from backtester.util.util import str_to_seconds


class LiveDataHandler(DataHandler):
    def __init__(self, event_queue: list, symbol_list: list, interval: str, period: str, exchange_closing_time: str):
        """
        Initializes the LiveDataHandler
        args:
            event_queue: the Event Queue
            symbol_list: a list of symbol strings
            interval: e.g. 5m means OHLC data for 5 minutes
            period: how long should the live data test run
            exchange_closing_time: 24h time format - HH:MM
        """
        self.event_queue = event_queue
        self.interval = str_to_seconds(interval)
        self.period = str_to_seconds(period)
        self.symbol_list = symbol_list
        self.exchange_closing_time = exchange_closing_time

        self.message_queue = Queue()
        self.bar_dict = {ticker: {} for ticker in symbol_list}  # {string: BarTuple}
        self.symbol_raw_data = {ticker: [] for ticker in symbol_list}  # {string: list[pd.DataFrame]}
        self.latest_symbol_data = {ticker: [] for ticker in symbol_list}  # {string: list[BarTuple]}
        self.continue_backtest = True

        message_listener = threading.Thread(target=self._start_listening, args=(symbol_list,))
        message_listener.daemon = True
        aggregator = threading.Thread(target=self._start_aggregating)
        aggregator.daemon = True
        self.beginning_time = datetime.now().timestamp()
        self.start_time = self.beginning_time
        self.end_time = self.start_time + self.interval - 1
        self.final_time = self.start_time + self.period
        message_listener.start()
        aggregator.start()

    def _start_aggregating(self):
        """
        Aggregates all messages from the websocket into a single bar
        """
        current_time = self.start_time
        while current_time < self.final_time:
            sleep_time = self.end_time - datetime.now().timestamp()  # negates drift as well
            if sleep_time > 0:
                time.sleep(sleep_time)  # sleep till end of interval
            print(f"Timestamp:: {self.start_time} <> {self.end_time}: {self.message_queue.qsize()} messages")
            while not self.message_queue.empty():
                message = self.message_queue.get(block=False)
                ticker = message["id"]
                price = message["price"]
                current_time = float(message["time"]) / 1000
                if not self.bar_dict[ticker]:  # if empty dictionary for that ticker. we are in a new interval, reset bar_dict
                    self.bar_dict[ticker] = {"Index": pd.to_datetime(self.start_time, unit="s").tz_localize(None), "open": price, "high": price, "low": price, "close": price}
                if current_time > self.end_time:  # we are in a new interval alr, break, and let the interval end handling happen below
                    break
                else:  # we are still in the same interval, continue updating high, low, and close prices
                    bar = self.bar_dict[ticker]
                    bar["high"] = max(bar["high"], price)
                    bar["low"] = max(bar["low"], price)
                    bar["close"] = price
            self._finalize_and_push_bars(self.start_time)
            self.start_time = self.end_time + 1
            self.end_time = self.start_time + self.interval - 1
            if self.end_time > self.final_time:
                break

        self.continue_backtest = False
        for key, val in self.symbol_raw_data.items():  # self.symbol_raw_data is a dictionry of ticker to dataframe
            df = pd.DataFrame(val)
            df.set_index("Index", inplace=True)
            self.symbol_raw_data[key] = df

    def _finalize_and_push_bars(self, start_time: float):
        """
        Pushes the latest bar to the latest_symbol_data structure for all
        symbols in the symbol list. This will also generate a MarketEvent.
        args:
            start_time: the start time of the interval
        """
        mkt_close = False
        for symbol in self.symbol_list:
            bar = self.bar_dict[symbol]
            if not bar:
                if len(self.latest_symbol_data[symbol]) > 0:  # if we have previous data and only this interval has no movement, use previous data
                    bar = self.latest_symbol_data[symbol][-1]._replace(Index=pd.to_datetime(start_time, unit="s"))
                else:  # if no previous data, then this interval will have no data as well
                    bar = None
            else:
                bar = BarTuple(**bar)

            if bar is not None:
                self.symbol_raw_data[symbol].append(bar)
                self.latest_symbol_data[symbol].append(bar)
                mkt_close = (
                  bar.Index + pd.Timedelta(self.interval) 
                  >= bar.Index.replace(
                    hour=int(self.exchange_closing_time.split(":")[0])
                    , minute=int(self.exchange_closing_time.split(":")[1])
                    )
                  )

            self.bar_dict[symbol] = {}  # reset for the next interval

        self.event_queue.put(MarketEvent(self.start_time, mkt_close))

    def update_bars(self):
        """
        In live trading, the background thread handles bar generation.
        This method is a stub to satisfy the DataHandler interface.
        """
        pass

    def get_latest_bars(self, symbol: str, n: int = 1):
        """
        Returns the last N bars from the latest_symbol_data
        """
        return self.latest_symbol_data[symbol][-n:]

    def _start_listening(self, symbol_list: list):
        with yf.WebSocket() as ws:
            ws.subscribe(symbol_list)
            ws.listen(self._handle_message)

    def _handle_message(self, message):
        """
        Handler for the message from the websocket. An example of the message from yf below
        {'id': 'AAPL', 'price': 239.8471, 'time': '1758116301000', 'exchange': 'NMS', 'quote_type': 8, 'market_hours': 1, 'change_percent': 0.7126236, 'day_volume': '3618459', 'change': 1.697113, 'price_hint': '2'}
        """
        self.message_queue.put(message)
