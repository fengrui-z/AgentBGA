"""Finite price-track markets with deterministic purchase and refill order."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class MarketQuote:
    requested: int
    track_units: int
    external_units: int
    unit_prices: tuple[int, ...]

    @property
    def total_price(self) -> int:
        return sum(self.unit_prices)


@dataclass
class MarketTrack:
    """A generic market whose slots carry prices and one unit at most.

    Purchase and refill order are explicit because different economic games
    orient otherwise similar market tracks differently.
    """

    prices: tuple[int, ...]
    occupied: list[bool]
    purchase_order: tuple[int, ...]
    refill_order: tuple[int, ...]
    external_price: int | None = None

    def __post_init__(self) -> None:
        size = len(self.prices)
        if len(self.occupied) != size:
            raise ValueError("market prices and occupied slots must have equal length")
        expected = set(range(size))
        if set(self.purchase_order) != expected or len(self.purchase_order) != size:
            raise ValueError("purchase order must contain every market slot exactly once")
        if set(self.refill_order) != expected or len(self.refill_order) != size:
            raise ValueError("refill order must contain every market slot exactly once")
        if any(not isinstance(price, int) or isinstance(price, bool) or price < 0
               for price in self.prices):
            raise ValueError("market prices must be non-negative integers")
        if self.external_price is not None and self.external_price < 0:
            raise ValueError("external market price must be non-negative")

    def quote(self, quantity: int) -> MarketQuote:
        if not isinstance(quantity, int) or isinstance(quantity, bool) or quantity < 0:
            raise ValueError("market quantity must be a non-negative integer")
        available = [index for index in self.purchase_order if self.occupied[index]]
        track = available[:quantity]
        external_units = quantity - len(track)
        if external_units and self.external_price is None:
            raise ValueError("market does not have enough supply")
        prices = [self.prices[index] for index in track]
        prices.extend([self.external_price] * external_units)
        return MarketQuote(quantity, len(track), external_units, tuple(prices))

    def consume(self, quantity: int) -> MarketQuote:
        quote = self.quote(quantity)
        track_slots = [index for index in self.purchase_order if self.occupied[index]][:quote.track_units]
        for index in track_slots:
            self.occupied[index] = False
        return quote

    def refill(self, quantity: int) -> MarketQuote:
        if not isinstance(quantity, int) or isinstance(quantity, bool) or quantity < 0:
            raise ValueError("market quantity must be a non-negative integer")
        empty = [index for index in self.refill_order if not self.occupied[index]][:quantity]
        for index in empty:
            self.occupied[index] = True
        return MarketQuote(quantity, len(empty), quantity - len(empty),
                           tuple(self.prices[index] for index in empty))
