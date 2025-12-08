from abc import ABC, abstractmethod


class RiskManager(ABC):
    @abstractmethod
    def is_allowed(self) -> bool:
        pass
