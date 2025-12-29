import collections
import queue
from copy import deepcopy

import pandas as pd

from backtester.enums.direction_type import DirectionType
from backtester.enums.order_type import OrderType
from backtester.events.order_event import OrderEvent
from backtester.exceptions.negative_cash_exception import NegativeCashException
from backtester.portfolios.portfolio import Portfolio
from backtester.util.util import get_annualization_factor
from backtester.util.position_sizer.position_sizer import PositionSizer
from backtester.util import util
from backtester.events.fill_event import FillEvent
from backtester.util.util import BarTuple
from backtester.util.risk_manager.risk_manager import RiskManager

class NaivePortfolio(Portfolio):
    """
    A naive portfolio implementation.
    """

    def __init__(
        self,
        cash_buffer: float,
        initial_capital: float,
        initial_position_size: float,
        symbol_list: list[str],
        rounding_list: list[int],
        events: queue.Queue,
        start_date: float,
        interval: str,
        metrics_interval: str,
        position_sizer: PositionSizer,
        strategy_name: str,
        risk_manager: RiskManager,
        allocation: float = 1,
        borrow_cost: float = 0.01,
        maintenance_margin: float = 0.5,
        risk_per_trade: float = 0.01,
    ):
        """
        Initializes the NaivePortfolio with initial capital, a list of symbols, an event queue, and allocation percentage.

        args:
          cash_buffer (float): 
          initial_capital (float): The starting capital for the portfolio.
          initial_position_size (float): Used by portfolio to size a trade in the absence of any other help
          symbol_list (list): List of ticker symbols to include in the portfolio.
          events (queue.Queue): The event queue to communicate with other components.
          start_date (float): The starting timestamp for the portfolio.
          interval (str):  one of the following - 1m, 2m, 5m, 15m, 30m, 60m, 90m, 1h, 1d, 5d, 1wk, 1mo, 3mo
          position_sizer:
          strategy_name: name of the strategy currently testing - TODO: enhance for multi strategy testing
          risk_manager: 
          allocation (float): The percentage of the portfolio that an asset is maximally allowed to take (default is 1).
          borrow_cost (float): The annualized interest rate for borrowing stocks to short sell (default is 0.01, i.e., 1%).
          maintenance_margin (float): The minimum equity percentage required to maintain a short position (default is 0.5, i.e., 50%).

        Attributes:
          daily_borrow_rate: the daily interest rate for borrowing stocks to short sell
          margin_holdings: tracks the margin held for each symbol when shorting
          current_holdings: polarity of values indicate a short (<0) or long (>0) position
        """
        self.MINUTES_IN_HOUR = 60.0
        self.TRD_HOURS_IN_DAY = 6.5
        self.TRD_DAYS_IN_YEAR = 252.0

        self.cash_buffer = cash_buffer
        self.initial_capital = initial_capital
        self.initial_position_size = initial_position_size
        self.symbol_list = symbol_list
        self.rounding_number = {ticker: rnd for ticker, rnd in zip(symbol_list, rounding_list)}
        self.events = events
        self.start_date = start_date
        self.interval = interval
        self.metrics_interval = metrics_interval
        self.allocation = allocation
        self.daily_borrow_rate = borrow_cost / get_annualization_factor(interval)  # assuming 252 trading days in a year
        self.maintenance_margin = maintenance_margin
        self.risk_per_trade = risk_per_trade
        self.position_sizer = position_sizer
        self.strategy_name = strategy_name
        self.risk_manager = risk_manager

        self.history = {}
        self.margin_holdings = collections.defaultdict(int) # up to date values of the margin held for each ticker
        self.position_dict = {sym: self.initial_position_size for sym in self.symbol_list}  # holds the position size last used (backup for sizer derivations)
        self.daily_open_value = collections.defaultdict(float)  # holds the opening value of each strategy - used in riskmanager pnl

        self.current_holdings = {sym: {"position": 0, "value": 0.0} for sym in self.symbol_list}
        self.current_holdings["margin"] = collections.defaultdict(int) # only updated with self.margin_holdings at the end of the day or when there is a new order
        self.current_holdings["cash"] = initial_capital
        self.current_holdings["total"] = initial_capital
        self.current_holdings["commissions"] = 0.0
        self.current_holdings["timestamp"] = start_date
        self.current_holdings["borrow_costs"] = 0.0
        self.current_holdings["order"] = ""
        self.current_holdings["slippage"] = ""
        self.historical_holdings = []

    def on_interval(self, histories: dict[str, list[BarTuple]]):
        if not self.history: # TODO: to check only once, not needed on every hearbeat
            self.history = histories
        self.on_market()

    def on_market(self):
        """
        TODO: can be made on demand instead? Does the RiskManager require on every heartbeat?
        This method is called whenever a new market event is received.
        Sets up the new phase of current_holdings by creating a new map object and placing the previous
        'current_holdings' into historical_holdings
        Also,
        The end of a trading interval e.g. 5mins, 1day - perform tasks that can only take place only take place at the END of the current interval
        Also, updates the value of currently held positions
        """
        self.current_holdings = deepcopy(self.current_holdings)
        self.current_holdings["commissions"] = 0.0
        self.current_holdings["borrow_costs"] = 0.0
        self.current_holdings["order"] = ""
        self.current_holdings["slippage"] = ""
        self.historical_holdings.append(self.current_holdings)

        for ticker in self.symbol_list:
            # Mark-to-market valuation at the end of the interval
            bar = self.history[(ticker, self.interval)][-1]
            initial_holding = self.current_holdings[ticker]["value"]
            self.current_holdings[ticker]["value"] = self.current_holdings[ticker]["position"] * bar.close
            self.current_holdings["total"] += self.current_holdings[ticker]["value"] - initial_holding
            self.current_holdings["timestamp"] = bar.Index

        if self.strategy_name not in self.daily_open_value:
            self.daily_open_value[self.strategy_name] = self.current_holdings["total"]

        if self.current_holdings["cash"] < 0:
            raise NegativeCashException(self.current_holdings["cash"])

    def on_signal(self, event):
        order = None
        ticker = event.ticker
        strategy_name = event.strategy
        order_type = OrderType.MKT
        cur_quantity = self.current_holdings[ticker]["position"]

        # Get quantity we would like to risk
        print(self.current_holdings["total"])
        target_quantity = self.position_sizer.get_position_size(self.risk_per_trade, self.current_holdings["total"], self.rounding_number[ticker], ticker)

        if target_quantity is None:
            target_quantity = self.position_dict[ticker]  # use the last used position size
        self.position_dict[ticker] = target_quantity  # update the last used position size

        target_quantity *= event.strength # apply signal strength

        bars = self.history[(ticker, self.interval)]
        if not bars:
            print(f"WARN: No data for {ticker}, cannot size position.")
            return
        estimated_price = bars[-1].close
        eff_cash_available = self.current_holdings["cash"]
        delta_quantity = target_quantity # the holdings we need our holdings to be at

        if event.signal_type.value == -1:  # SHORT
            if cur_quantity > 0:  # currently LONG, need to exit first
                eff_cash_available += cur_quantity * estimated_price # cash received from selling what is currently held
                target_quantity += cur_quantity
            order = OrderEvent(DirectionType(-1), ticker, strategy_name, order_type, target_quantity, event.timestamp)
        elif event.signal_type.value == 1:  # LONG
            if cur_quantity < 0:  # currently SHORT, need to exit first
                eff_cash_available += self.margin_holdings[ticker] # margin held for short position is released
                target_quantity += abs(cur_quantity)
            order = OrderEvent(DirectionType(1), ticker, strategy_name, order_type, target_quantity, event.timestamp)
        else:  # EXIT
            if cur_quantity > 0:  # EXIT a long position
                order = OrderEvent(DirectionType(-1), ticker, strategy_name, order_type, cur_quantity, event.timestamp)
            elif cur_quantity < 0:  # EXIT a short position
                order = OrderEvent(DirectionType(1), ticker, strategy_name, order_type, abs(cur_quantity), event.timestamp)

        if estimated_price > 0:
            if order.direction == DirectionType.BUY:
                max_affordable_qty = (eff_cash_available * self.cash_buffer) / estimated_price
            elif order.direction == DirectionType.SELL:
                max_affordable_qty = (eff_cash_available * self.cash_buffer) / (1 + self.maintenance_margin * estimated_price)
            # clamp. We can't buy more than cash allows or sell more than the margin that can be afforded
            if target_quantity > max_affordable_qty:
                print(f"WARN: Sizer requested {target_quantity}, but maximum affordable qty is {max_affordable_qty}. Clamping.")
                order.quantity = max_affordable_qty

        if order and self.risk_manager.is_allowed(order, self.daily_open_value, bars, self.symbol_list, self.current_holdings):
            print(f"=== PORTFOLIO ORDER: dir: {order.direction} qty: {order.quantity}, type: {order.order_type} ===")
            self.events.put(order)

    def on_fill(self, event: FillEvent):
        """
        Updates the portfolio's positions and holdings based on a FillEvent.
        """
        initial_holding = self.current_holdings[event.ticker]["value"]

        # Update position and cash
        self.current_holdings[event.ticker]["position"] += event.direction.value * event.quantity
        cash_delta = -1 * event.direction.value * event.fill_cost - event.commission
        self.current_holdings["cash"] += cash_delta
        self.current_holdings["commissions"] += event.commission

        # Update portfolio value based on fill, not latest close
        self.current_holdings[event.ticker]["value"] = self.current_holdings[event.ticker]["position"] * event.unit_cost
        self.current_holdings["total"] += self.current_holdings[event.ticker]["value"] - initial_holding + cash_delta

        self.current_holdings["order"] += f"{event.direction.name} {event.quantity} {event.ticker} @ {event.unit_cost:,.2f} | "

        self.current_holdings["slippage"] += f"{event.slippage} | "

        # MARGIN
        if self.current_holdings[event.ticker]["position"] < 0:  # nett SHORT position
            margin_diff = self.margin_holdings[event.ticker] + (self.current_holdings[event.ticker]["value"]) * (1 + self.maintenance_margin)  # margin change
            self.current_holdings["cash"] += margin_diff  # cash frozen for margin, reduction if margin_diff is -ve
            self.margin_holdings[event.ticker] -= margin_diff
        else:  # nett LONG position
            self.current_holdings["cash"] += self.margin_holdings[event.ticker]  # total portfolio value is inclusive of margin - elease any margin being held
            self.margin_holdings[event.ticker] = 0  # reset margin

        self.current_holdings["margin"] = self.margin_holdings.copy()

    def end_of_day(self):
        """
        The end of the trading day - perform mark to market activities like margin calculation and borrow costs
        Also, updates the value of currently held positions
        """
        self.current_holdings["total"] = 0  # recalculate
        for ticker in self.symbol_list:
            latest_bar = self.history[(ticker, self.interval)][-1]
            self.current_holdings[ticker]["value"] = self.current_holdings[ticker]["position"] * latest_bar.close
            self.current_holdings["total"] += self.current_holdings[ticker]["value"]  # add value of current position
            if self.current_holdings[ticker]["position"] < 0:  # nett SHORT position
                # MARGIN
                margin_diff = self.margin_holdings[ticker] + (self.current_holdings[ticker]["value"]) * (1 + self.maintenance_margin)  # margin change
                self.current_holdings["cash"] += margin_diff  # cash frozen for margin, reduction if margin_diff is -ve
                self.margin_holdings[ticker] -= margin_diff
                self.current_holdings["total"] += self.margin_holdings[ticker]  # total portfolio value is inclusive of margin
                # BORROW COSTS
                daily_borrow_cost = abs(self.current_holdings[ticker]["value"]) * self.daily_borrow_rate
                self.current_holdings["cash"] -= daily_borrow_cost
                self.current_holdings["borrow_costs"] += daily_borrow_cost
            else:  # nett LONG position
                self.current_holdings["cash"] += self.margin_holdings[ticker]  # release any margin being held
                self.margin_holdings[ticker] = 0  # reset margin
        self.current_holdings["total"] += self.current_holdings["cash"]
        # self.current_holdings["margin"] = self.margin_holdings.copy()
        self.daily_open_value = collections.defaultdict(float)  # reset the daily pnl dictionary


    def create_equity_curve(self):
        curve = pd.DataFrame(self.historical_holdings)
        curve["timestamp"] = pd.to_datetime(curve["timestamp"], unit="s")
        curve.set_index("timestamp", inplace=True)
        curve = curve.resample(util.str_to_pandas(self.metrics_interval)).agg(self._form_dict())
        curve["returns"] = curve["total"].pct_change().fillna(0.0)
        curve["equity_curve"] = (1.0 + curve["returns"]).cumprod()
        self.equity_curve = curve

    def _form_dict(self):
        d = {ticker: "last" for ticker in self.symbol_list}
        d["margin"] = "last"
        d["cash"] = "last"
        d["total"] = "last"
        d["commissions"] = lambda x: " + ".join([str(comms) for comms in x if comms != 0.0])
        d["borrow_costs"] = lambda x: " + ".join([str(bcosts) for bcosts in x if bcosts != 0.0])
        d["order"] = lambda x: " | ".join([order for order in x if order is not None and order != ""])
        d["slippage"] = lambda x: " | ".join([slippage for slippage in x if slippage is not None and slippage != ""])
        return d

    def liquidate(self):
        self.current_holdings = deepcopy(self.current_holdings)
        self.current_holdings["timestamp"] = pd.to_datetime(self.current_holdings["timestamp"], unit="s") + pd.Timedelta(self.interval)
        self.current_holdings["timestamp"] = self.current_holdings["timestamp"].timestamp()
        self.current_holdings["commissions"] = 0.0
        self.current_holdings["borrow_costs"] = 0.0
        self.current_holdings["order"] = ""
        self.historical_holdings.append(self.current_holdings)
        for ticker in self.symbol_list:
            latest_bar = self.history[(ticker, self.interval)][-1]
            if self.current_holdings[ticker]["position"] < 0:  # nett SHORT position
                self.current_holdings["cash"] += self.margin_holdings[ticker]  # release any margin being held
                self.margin_holdings[ticker] = 0
            self.current_holdings["cash"] += self.current_holdings[ticker]["position"] * latest_bar.close
            self.current_holdings[ticker]["position"] = 0
            self.current_holdings[ticker]["value"] = 0
            self.current_holdings["margin"][ticker] = 0
        self.current_holdings["total"] = self.current_holdings["cash"]
