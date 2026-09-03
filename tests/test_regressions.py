"""Regression tests.

Each test here pins down a bug that was present in fxreport 0.3.1. Every one of
them fails against the original code and passes after the corresponding fix.
"""

from datetime import date

import pytest

from fxreport.report import date_range, render, weekly_averages


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


def test_weekly_average_keeps_daily_precision() -> None:
    """Bug 2: weekly_averages() rounded every *daily* rate to 2 decimals before
    averaging, so sub-cent moves were discarded. GBP rates (~0.86) collapsed to
    a constant 0.8600 and the rendered 4-decimal output was simply wrong."""
    rates = {
        "2024-01-02": {"GBP": 0.86645},
        "2024-01-03": {"GBP": 0.86470},
        "2024-01-04": {"GBP": 0.86278},
        "2024-01-05": {"GBP": 0.86210},
    }
    weekly = weekly_averages(rates, ["GBP"])
    expected = (0.86645 + 0.86470 + 0.86278 + 0.86210) / 4
    assert weekly["2024-W01"]["GBP"] == pytest.approx(expected)
    # The buggy version rounded each input to 0.86 and averaged to exactly 0.86.
    assert weekly["2024-W01"]["GBP"] != pytest.approx(0.86, abs=1e-9)


def test_render_shows_distinct_weekly_values() -> None:
    """Bug 2, end to end: two weeks with genuinely different averages must not
    render as the same number."""
    rates = {
        "2024-01-02": {"USD": 1.0956},
        "2024-01-03": {"USD": 1.0919},
        "2024-01-08": {"USD": 1.0946},
        "2024-01-09": {"USD": 1.0943},
    }
    out = render(weekly_averages(rates, ["USD"]), ["USD"])
    week_values = [line.split()[1] for line in out.splitlines()[2:]]
    assert week_values == ["1.0938", "1.0945"]
