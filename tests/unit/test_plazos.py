"""Unit tests for business-day calculations and statutory terms under Colombian law.

Covers:
- add_business_days: skipping weekends and official holidays
- is_business_day: weekday and holiday detection
- invalid inputs: days < 1 raising ValueError
"""
from __future__ import annotations

from datetime import date

import pytest

from app.domain.plazos import WEEKEND, add_business_days, is_business_day


def test_add_business_days_within_same_week() -> None:
    """Monday + 3 business days should be Thursday of the same week."""
    monday = date(2026, 3, 2)
    assert monday.weekday() == 0  # Monday

    thursday = add_business_days(monday, 3)
    assert thursday == date(2026, 3, 5)
    assert thursday.weekday() == 3  # Thursday


def test_add_business_days_skips_weekends() -> None:
    """Term filed on Friday starts on Monday (+1) and skips Saturday and Sunday."""
    friday = date(2026, 3, 6)
    assert friday.weekday() == 4  # Friday

    # +1 day skips Sat (Mar 7) and Sun (Mar 8) -> Mon (Mar 9)
    assert add_business_days(friday, 1) == date(2026, 3, 9)

    # +2 days -> Tue (Mar 10)
    assert add_business_days(friday, 2) == date(2026, 3, 10)

    # +5 days (full week) -> Fri (Mar 13)
    assert add_business_days(friday, 5) == date(2026, 3, 13)

    # +6 days -> Mon (Mar 16)
    assert add_business_days(friday, 6) == date(2026, 3, 16)


def test_add_business_days_skips_holidays() -> None:
    """Holidays falling on weekdays are excluded from term calculation."""
    friday = date(2026, 3, 6)
    monday_holiday = date(2026, 3, 9)
    tuesday_holiday = date(2026, 3, 10)

    # Friday + 1 day with Monday holiday -> Tuesday
    res1 = add_business_days(friday, 1, holidays=[monday_holiday])
    assert res1 == date(2026, 3, 10)

    # Friday + 1 day with Monday AND Tuesday holidays -> Wednesday
    res2 = add_business_days(friday, 1, holidays=[monday_holiday, tuesday_holiday])
    assert res2 == date(2026, 3, 11)


def test_add_business_days_statutory_15_days() -> None:
    """Standard Colombian statutory term of 15 business days (Resolución 369)."""
    start = date(2026, 3, 2)  # Monday
    # 15 business days = 3 full weeks (5 business days per week) -> Monday 3 weeks later
    expected = date(2026, 3, 23)
    assert add_business_days(start, 15) == expected


def test_add_business_days_rejects_zero_or_negative() -> None:
    """Counting business days requires days >= 1, else raises ValueError."""
    today = date(2026, 3, 6)
    with pytest.raises(ValueError) as exc_zero:
        add_business_days(today, 0)
    assert "days must be at least 1" in str(exc_zero.value)

    with pytest.raises(ValueError) as exc_neg:
        add_business_days(today, -5)
    assert "days must be at least 1" in str(exc_neg.value)


def test_is_business_day() -> None:
    """Verify is_business_day behavior for weekdays, weekends, and holidays."""
    friday = date(2026, 3, 6)
    saturday = date(2026, 3, 7)
    sunday = date(2026, 3, 8)
    monday = date(2026, 3, 9)

    # Regular weekdays
    assert is_business_day(friday) is True
    assert is_business_day(monday) is True

    # Weekends (Saturday=5, Sunday=6)
    assert is_business_day(saturday) is False
    assert is_business_day(sunday) is False
    assert saturday.weekday() in WEEKEND
    assert sunday.weekday() in WEEKEND

    # Weekday that is a holiday
    assert is_business_day(monday, holidays=[monday]) is False
