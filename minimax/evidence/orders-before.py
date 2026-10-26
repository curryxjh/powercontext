"""Order listing for a small shop."""

from dataclasses import dataclass


@dataclass(frozen=True)
class Order:
    number: str
    status: str


def list_orders(orders: list[Order], status: str | None = None) -> list[Order]:
    """Return orders in their original order."""
    return list(orders)
