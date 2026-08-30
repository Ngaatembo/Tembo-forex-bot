"""
Broker execution abstraction.

CRITICAL SAFETY NOTE:
This module intentionally does not implement any real-money broker
connection in Phase 0. `get_broker_adapter()` only ever returns the
paper broker unless BOTH:

  1. settings.enable_live_execution is explicitly True, AND
  2. a real adapter has actually been implemented and registered below

Do not remove this guard. Live execution must require a deliberate,
explicit configuration change — never a default.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Optional

from app.core.config import get_settings


@dataclass
class Order:
    symbol: str
    direction: str  # BUY | SELL
    size: float
    stop_loss: Optional[float] = None
    take_profit: Optional[float] = None


@dataclass
class Position:
    symbol: str
    direction: str
    size: float
    entry_price: float


class BrokerAdapter(ABC):
    @abstractmethod
    async def get_account(self) -> dict:
        ...

    @abstractmethod
    async def get_positions(self) -> list[Position]:
        ...

    @abstractmethod
    async def place_order(self, order: Order) -> dict:
        ...

    @abstractmethod
    async def cancel_order(self, order_id: str) -> dict:
        ...

    @abstractmethod
    async def modify_order(self, order_id: str, **changes) -> dict:
        ...

    @abstractmethod
    async def close_position(self, symbol: str) -> dict:
        ...


class PaperBrokerAdapter(BrokerAdapter):
    """
    Mock/paper broker. This is the only adapter wired up in Phase 0.
    Real paper-trading simulation logic (balance, P&L, slippage) lands
    in app/paper_trading in a later phase — this class is currently a
    structural placeholder implementing the interface.
    """

    async def get_account(self) -> dict:
        return {"balance": 10000.0, "currency": "USD", "mode": "paper"}

    async def get_positions(self) -> list[Position]:
        return []

    async def place_order(self, order: Order) -> dict:
        return {"status": "simulated", "order": order.__dict__}

    async def cancel_order(self, order_id: str) -> dict:
        return {"status": "simulated_cancel", "order_id": order_id}

    async def modify_order(self, order_id: str, **changes) -> dict:
        return {"status": "simulated_modify", "order_id": order_id, "changes": changes}

    async def close_position(self, symbol: str) -> dict:
        return {"status": "simulated_close", "symbol": symbol}


def get_broker_adapter() -> BrokerAdapter:
    settings = get_settings()
    if not settings.enable_live_execution:
        return PaperBrokerAdapter()

    # A real broker adapter would be selected and returned here once
    # implemented. Left unimplemented deliberately for Phase 0 — live
    # execution requires code that does not exist yet, not just a flag.
    raise NotImplementedError(
        "Live execution is enabled in configuration but no live broker "
        "adapter has been implemented. This is intentional — see "
        "docs/risk-management.md."
    )
