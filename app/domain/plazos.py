"""Business-day arithmetic for PQRSD deadlines and statutory terms.

The legal terms of Resolucion 369 de 2019 are counted in business days, so
weekends and the ``festivo`` catalog are excluded. The functions are pure:
the caller loads the holidays from the database or domain repository.
"""
from __future__ import annotations

from collections.abc import Iterable
from datetime import date, timedelta

WEEKEND = frozenset({5, 6})  # Saturday (5), Sunday (6) in date.weekday()


def add_business_days(
    start: date, days: int, holidays: Iterable[date] = ()
) -> date:
    """Return the date ``days`` business days after ``start``.

    Counting begins the day after ``start``, which matches Colombian
    administrative procedure where a petition filed on day T starts its
    term on the following business day T+1.
    """
    if days < 1:
        raise ValueError("days must be at least 1")

    excluded = set(holidays)
    current = start
    remaining = days
    while remaining > 0:
        current += timedelta(days=1)
        if current.weekday() not in WEEKEND and current not in excluded:
            remaining -= 1
    return current


def is_business_day(value: date, holidays: Iterable[date] = ()) -> bool:
    """Whether ``value`` is a weekday (Monday-Friday) not in ``holidays``."""
    return value.weekday() not in WEEKEND and value not in set(holidays)


__all__ = [
    "WEEKEND",
    "add_business_days",
    "is_business_day",
]
