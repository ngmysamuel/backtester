from enum import Enum


class SignalType(Enum):
  LONG = 1
  SHORT = -1
  HOLD = 0
  EXIT = -2