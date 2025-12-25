class NegativeCashException(Exception):
    """Custom exception raised when an account has insufficient funds."""

    def __init__(self, current_cash: float = -1, message: str = "Insufficient cash in the account"):
        super().__init__(message)  # Call the base Exception's constructor
        self.current_cash = current_cash
        self.message = f"{message}: {current_cash}"  # Store the message for potential display

    def __str__(self) -> str:
        return self.message
