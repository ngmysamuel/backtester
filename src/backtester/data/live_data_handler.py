import queue
import threading
import time
from datetime import datetime
from queue import Queue
from typing import Any, Optional

import pandas as pd
import yfinance as yf  # type: ignore

from backtester.data.data_handler import DataHandler
from backtester.events.event import Event
from backtester.events.market_event import MarketEvent
from backtester.util.util import BarDict, BarTuple, str_to_seconds, SentimentTuple


class LiveDataHandler(DataHandler):
    def __init__(self, event_queue: queue.Queue[Event], **kwargs):
        """
        Initializes the LiveDataHandler
        args:
            event_queue: the Event Queue
            symbol_list: list[str] - a list of symbol strings
            interval: str - e.g. 5m means OHLC data for 5 minutes
            period: str - how long should the live data test run
            exchange_closing_time: str - 24h time format - HH:MM
        """
        self.event_queue = event_queue
        self.interval = str_to_seconds(kwargs["base_interval"])
        self.period = str_to_seconds(kwargs["period"])
        self.symbol_list = kwargs["symbol_list"]
        self.exchange_closing_time = kwargs["exchange_closing_time"]

        self.message_queue: queue.Queue[Any] = Queue()
        self.symbol_bar_dict: dict[str, Optional[BarDict]] = {ticker: None for ticker in self.symbol_list}  # {string: BarDict}
        self.symbol_raw_data: dict[str, list[Optional[BarTuple]] | pd.DataFrame] = {ticker: [] for ticker in self.symbol_list}  # {string: list[pd.DataFrame]}
        self.latest_symbol_data: dict[str, list[BarTuple]] = {ticker: [] for ticker in self.symbol_list}  # {string: list[BarTuple]}
        self.continue_backtest = True
        self.day_vol: dict[str, int] = {ticker: 0 for ticker in self.symbol_list} # {string: int}
        self.interval_vol: dict[str, int] = {ticker: 0 for ticker in self.symbol_list} # {string: int}

        message_listener = threading.Thread(target=self._start_listening, args=(self.symbol_list,))
        message_listener.daemon = True
        aggregator = threading.Thread(target=self._start_aggregating)
        aggregator.daemon = True
        self.beginning_time = datetime.now().timestamp()
        self.start_time = self.beginning_time
        self.end_time = self.start_time + self.interval - 1
        self.final_time = self.start_time + self.period
        message_listener.start()
        aggregator.start()

    def _start_aggregating(self) -> None:
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
                try:
                    message_vol = int(message["day_volume"])
                except KeyError:
                    print(f"message has no day_volume key: {message}")
                    message_vol = self.day_vol[ticker] # if no volume data, we just assume there is no volume
                if message_vol >= self.day_vol[ticker]: # start of a new day, no prior intervals / valid volume information
                    if self.day_vol[ticker] == 0 :
                        self.day_vol[ticker] = message_vol # init the day volume - starting the engine in the middle of the day
                    self.interval_vol[ticker] = max(self.interval_vol[ticker], message_vol - self.day_vol[ticker])
                current_time = float(message["time"]) / 1000
                if self.symbol_bar_dict[ticker] is None:  # if empty dictionary for that ticker. we are in a new interval, reset bar_dict
                    self.symbol_bar_dict[ticker] = {"Index": pd.to_datetime(self.start_time, unit="s").tz_localize(None), "open": price, "high": price, "low": price, "close": price, "volume": self.interval_vol[ticker], "raw_volume": message_vol, "sentiment": SentimentTuple(Index=datetime.now(), score=0.0)}
                if current_time > self.end_time:  # we are in a new interval alr, break, and let the interval end handling happen below
                    break
                else:  # we are still in the same interval, continue updating high, low, and close prices
                    bar = self.symbol_bar_dict[ticker]
                    if bar is not None:
                        bar["high"] = max(bar["high"], price)
                        bar["low"] = min(bar["low"], price)
                        bar["close"] = price
                        bar["volume"] = self.interval_vol[ticker]
            self._finalize_and_push_bars(self.start_time)
            self.start_time = self.end_time + 1
            self.end_time = self.start_time + self.interval - 1
            if self.end_time > self.final_time:
                break

        self.continue_backtest = False
        for key, val in self.symbol_raw_data.items():  # self.symbol_raw_data is a dictionary of ticker to dataframe
            df = pd.DataFrame(val)
            if "Index" in df.columns:
                df.set_index("Index", inplace=True)
            self.symbol_raw_data[key] = df

    def _finalize_and_push_bars(self, start_time: float) -> None:
        """
        Pushes the latest bar to the latest_symbol_data structure for all
        symbols in the symbol list. This will also generate a MarketEvent.
        args:
            start_time: the start time of the interval
        """
        mkt_close = False
        for symbol in self.symbol_list:
            bar_data: Optional[BarDict] = self.symbol_bar_dict[symbol]
            final_bar: Optional[BarTuple] = None

            if bar_data is None:
                if len(self.latest_symbol_data[symbol]) > 0:  # if we have previous data and only this interval has no movement, use previous data
                    final_bar = self.latest_symbol_data[symbol][-1]._replace(Index=pd.to_datetime(start_time, unit="s"))
                else:  # if no previous data, then this interval will have no data as well
                    final_bar = None
            else:
                final_bar = BarTuple(**bar_data)

            print(f"final bar: {final_bar}")
            if final_bar is not None:
                self.symbol_raw_data[symbol].append(final_bar)
                self.latest_symbol_data[symbol].append(final_bar)
                close_hour = int(self.exchange_closing_time.split(":")[0])
                close_minute = int(self.exchange_closing_time.split(":")[1])
                
                current_idx = final_bar.Index
                next_bar_time = current_idx + pd.Timedelta(self.interval, unit="s")

                market_close_time = current_idx.replace(hour=close_hour, minute=close_minute)

                mkt_close = next_bar_time >= market_close_time
            
            if mkt_close: # reset day volume information
                self.day_vol[symbol] = 0
            else: # increment volume traded today so far by the volume traded in the last interval
                self.day_vol[symbol] += self.interval_vol[symbol]

            # reset for the next interval
            self.symbol_bar_dict[symbol] = None
            self.interval_vol[symbol] = 0

        self.event_queue.put(MarketEvent(self.start_time, mkt_close))

    def update_bars(self) -> None:
        """
        In live trading, the background thread handles bar generation.
        This method is a stub to satisfy the DataHandler interface.
        """
        pass

    def get_latest_bars(self, symbol: str, n: int = 1) -> list[BarTuple]:
        """
        Returns the last N bars from the latest_symbol_data
        """
        return self.latest_symbol_data[symbol][-n:]

    def _start_listening(self, symbol_list: list[str]) -> None:
        with yf.WebSocket() as ws:
            ws.subscribe(symbol_list)
            ws.listen(self._handle_message)

    def _handle_message(self, message: dict[str, Any]) -> None:
        """
        Handler for the message from the websocket. Examples of the message from yf below
        {'id': 'AAPL', 'price': 239.8471, 'time': '1758116301000', 'exchange': 'NMS', 'quote_type': 8, 'market_hours': 1, 'change_percent': 0.7126236, 'day_volume': '3618459', 'change': 1.697113, 'price_hint': '2'}
        {'id': 'BTC-USD', 'price': 89633.69, 'time': '1764996000000', 'currency': 'USD', 'exchange': 'CCC', 'quote_type': 41, 'market_hours': 1, 'change_percent': -2.5575025, 'day_volume': '62136492032', 'day_high': 89793.9, 'day_low': 89124.484, 'change': -2352.5547, 'open_price': 89360.836, 'last_size': '62136492032', 'price_hint': '2', 'vol_24hr': '62136492032', 'vol_all_currencies': '62136492032', 'from_currency': 'BTC', 'circulating_supply': 19958140.0, 'market_cap': 1788921640000.0}
        """
        self.message_queue.put(message)
