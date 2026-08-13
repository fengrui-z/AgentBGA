"""Resource-ledger operations shared by economic games."""

from __future__ import annotations

from collections.abc import Mapping, MutableMapping
from itertools import product


def validate_resource_pool(
    pool: Mapping[str, int], *, expected_keys: set[str] | None = None, label: str = "resource pool",
) -> None:
    if expected_keys is not None and set(pool) != expected_keys:
        raise AssertionError(f"invalid resource keys at {label}")
    if any(not isinstance(amount, int) or isinstance(amount, bool) or amount < 0
           for amount in pool.values()):
        raise AssertionError(f"invalid resources at {label}")


def adjust_resources(pool: MutableMapping[str, int], changes: Mapping[str, int]) -> None:
    """Atomically apply signed deltas, rejecting missing or negative resources."""
    unknown = set(changes) - set(pool)
    if unknown:
        raise KeyError(f"unknown resources: {', '.join(sorted(unknown))}")
    after = {name: pool[name] + delta for name, delta in changes.items()}
    if any(amount < 0 for amount in after.values()):
        raise ValueError("resource adjustment would make a balance negative")
    pool.update(after)


def transfer_resources(
    source: MutableMapping[str, int], destination: MutableMapping[str, int],
    amounts: Mapping[str, int],
) -> None:
    """Atomically transfer non-negative amounts between two resource pools."""
    if any(not isinstance(amount, int) or isinstance(amount, bool) or amount < 0
           for amount in amounts.values()):
        raise ValueError("resource transfers require non-negative integer amounts")
    unknown = set(amounts) - (set(source) & set(destination))
    if unknown:
        raise KeyError(f"unknown resources: {', '.join(sorted(unknown))}")
    if any(source[name] < amount for name, amount in amounts.items()):
        raise ValueError("resource transfer exceeds source balance")
    source.update({name: source[name] - amount for name, amount in amounts.items()})
    destination.update({name: destination[name] + amount for name, amount in amounts.items()})


def discounted_cost(cost: Mapping[str, int], discounts: Mapping[str, int] | None = None) -> dict[str, int]:
    """Apply per-resource discounts without allowing a cost below zero."""
    discounts = discounts or {}
    unknown = set(discounts) - set(cost)
    if unknown:
        raise KeyError(f"discounts contain unknown resources: {', '.join(sorted(unknown))}")
    return {name: max(0, amount - discounts.get(name, 0)) for name, amount in cost.items()}


def payment_options(
    cost: Mapping[str, int], available: Mapping[str, int], *,
    discounts: Mapping[str, int] | None = None, wildcard: str | None = None,
) -> list[dict[str, int]]:
    """Enumerate deterministic payments for a multi-resource cost.

    A wildcard pays any shortfall after ordinary resources.  This captures
    Splendor gold and similar mechanisms while leaving location/network-based
    resource acquisition to game-specific legality policies.
    """
    due = discounted_cost(cost, discounts)
    ordinary = tuple(due)
    required_keys = set(ordinary) | ({wildcard} if wildcard else set())
    missing = required_keys - set(available)
    if missing:
        raise KeyError(f"available pool is missing resources: {', '.join(sorted(missing))}")
    choices = [range(min(due[name], available[name]) + 1) for name in ordinary]
    results: list[dict[str, int]] = []
    for amounts in product(*choices):
        shortfall = sum(due[name] - amounts[index] for index, name in enumerate(ordinary))
        if wildcard is None and shortfall:
            continue
        if wildcard is not None and shortfall > available[wildcard]:
            continue
        payment = {name: amounts[index] for index, name in enumerate(ordinary) if amounts[index]}
        if wildcard is not None and shortfall:
            payment[wildcard] = shortfall
        results.append(payment)
    results.sort(key=lambda payment: (
        payment.get(wildcard, 0) if wildcard else 0,
        tuple((name, payment[name]) for name in sorted(payment)),
    ))
    return results
