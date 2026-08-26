"""Mechanics data for Ark Nova's shared appeal/conservation scoring track."""

from __future__ import annotations


APPEAL_MAXIMUM = 113
CONSERVATION_MAXIMUM = 41
REPUTATION_MAXIMUM = 15
REPUTATION_DISPLAY_RANGES: tuple[tuple[int, int], ...] = (
    (1, 1), (2, 3), (4, 6), (7, 9), (10, 12), (13, 15),
)

# Minimum Appeal required for each printed Break-income value.  From Appeal 32
# the income rises every four spaces; from Appeal 56 it rises every five.
APPEAL_INCOME_THRESHOLDS: tuple[tuple[int, int], ...] = tuple(zip(
    (
        0, 1, 2, 3, 4, 5,
        7, 9, 11, 13, 15, 17,
        20, 23, 26, 29,
        32, 36, 40, 44, 48, 52, 56,
        61, 66, 71, 76, 81, 86, 91, 96, 101, 106, 111,
    ),
    range(5, 39),
))


def appeal_income(appeal: int) -> int:
    """Return printed Break money for an Appeal position."""

    position = max(0, min(APPEAL_MAXIMUM, appeal))
    income = 5
    for threshold, value in APPEAL_INCOME_THRESHOLDS:
        if threshold > position:
            break
        income = value
    return income


def conservation_score_offset(conservation: int) -> int:
    """Return the printed score offset for a Conservation position.

    Conservation 0 is the separately printed -13 starting space.  Spaces
    1--10 then run from -12 to +6 in steps of two; spaces 11--41 advance by
    three.
    """

    position = max(0, min(CONSERVATION_MAXIMUM, conservation))
    if position == 0:
        return -13
    return -14 + 2 * position if position <= 10 else -24 + 3 * position


def conservation_target_appeal(conservation: int) -> int:
    """Map a Conservation counter to the opposing Appeal-track coordinate."""

    return 100 - conservation_score_offset(conservation)


def scoring_tracks_crossed(appeal: int, conservation: int) -> bool:
    """Whether the opposing Appeal and Conservation counters meet or cross."""

    return appeal >= conservation_target_appeal(conservation)


def reputation_display_slot(reputation: int) -> int:
    """Return the highest display slot inside a player's Reputation range."""

    position = max(1, min(REPUTATION_MAXIMUM, reputation))
    return next(
        slot for slot, (_, maximum) in enumerate(REPUTATION_DISPLAY_RANGES, 1)
        if position <= maximum
    )
