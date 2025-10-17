from abc import ABC


class FillEvent(ABC):
  """
  Encapsulates the notion of a Filled Order, as returned
  from a brokerage. Stores the quantity of an instrument
  actually filled and at what price. In addition, stores
  the commission of the trade from the brokerage.
  """

  def __init__(
    self, timestamp, ticker, exchange, quantity, direction, fill_cost, unit_cost, slippage: float = 0.0, commission=None
  ):
    """
    Initialises the FillEvent object. Sets the ticker, exchange,
    quantity, direction, cost of fill and an optional
    commission.

    If commission is not provided, the Fill object will
    calculate it based on the trade size and Interactive
    Brokers fees.

    Parameters:
    timestamp - Timestamp when the order was filled.
    ticker - The instrument which was filled.
    exchange - The exchange where the order was filled.
    quantity - The filled quantity.
    direction - The direction of fill ('BUY' or 'SELL')
    fill_cost - The holdings value in dollars.
    unit_cost - The price of a single stock that was bought/sold
    slippage - the simulated slippage between bid and ask
    commission - An optional commission sent from IB.
    """

    self.type = "FILL"
    self.timestamp = timestamp
    self.ticker = ticker
    self.exchange = exchange
    self.quantity = quantity
    self.direction = direction
    self.fill_cost = fill_cost
    self.unit_cost = unit_cost
    self.slippage = slippage

    # Calculate commission
    if commission is None:
      self.commission = self.calculate_ib_commission()
    else:
      self.commission = commission

  def calculate_ib_commission(self):
    """
    Calculates the fees of trading based on an Interactive
    Brokers fee structure for API, in USD.

    This does not include exchange or ECN fees.

    Based on "US API Directed Orders":
    https://www.interactivebrokers.com/en/index.php?f=commission&p=stocks2
    """
    full_cost = 1.3
    if self.quantity <= 500:
      full_cost = max(1.3, 0.013 * self.quantity)
    else:  # Greater than 500
      full_cost = max(1.3, 0.008 * self.quantity)
    full_cost = min(full_cost, 0.5 / 100.0 * self.quantity * self.fill_cost)
    return full_cost
