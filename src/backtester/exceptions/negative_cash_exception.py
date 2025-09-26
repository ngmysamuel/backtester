class NegativeCashException(Exception):
    """Custom exception raised when an account has insufficient funds."""

    def __init__(self, current_cash: float = -1, message: str = "Insufficient cash in the account."):
        super().__init__(message)  # Call the base Exception's constructor
        self.current_cash = current_cash
        self.message = message # Store the message for potential display