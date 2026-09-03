"""Regression tests.

Each test here pins down a bug that was present in fxreport 0.3.1. Every one of
them fails against the original code and passes after the corresponding fix.
"""

from datetime import date

from fxreport.report import date_range


def test_date_range_includes_end_date() -> None:
    """Bug 1: date_range() dropped the final day despite documenting an
    inclusive range (it used range(n) instead of range(n + 1))."""
    days = date_range(date(2024, 1, 1), date(2024, 1, 5))
    assert days[0] == date(2024, 1, 1)
    assert days[-1] == date(2024, 1, 5)
    assert len(days) == 5


def test_date_range_single_day() -> None:
    """A start == end range is one day, not zero days."""
    assert date_range(date(2024, 3, 7), date(2024, 3, 7)) == [date(2024, 3, 7)]
