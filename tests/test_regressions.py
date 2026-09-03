"""Regression tests.

Each test here pins down a bug that was present in fxreport 0.3.1. Every one of
them fails against the original code and passes after the corresponding fix.
"""

from datetime import date

import pytest
import requests

from fxreport import cli, client
from fxreport import report as report_module
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


class _FakeResponse:
    def __init__(self, payload: dict[str, object], status: int = 200) -> None:
        self._payload = payload
        self.status_code = status

    def raise_for_status(self) -> None:
        if self.status_code >= 400:
            raise requests.HTTPError(f"{self.status_code} error")

    def json(self) -> dict[str, object]:
        return self._payload


def test_fetch_rates_drops_days_outside_requested_range(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Bug 3: Frankfurter extends a range backwards to the previous business
    day, so a Monday-holiday start such as 2024-01-01 comes back with
    2023-12-29 attached. fetch_rates() passed that straight through, seeding
    the cache with out-of-range days and (for any caller not re-filtering via
    the cache) inventing a spurious 2023-W52 row in the report."""
    payload = {
        "base": "EUR",
        "rates": {
            "2023-12-29": {"USD": 1.1050},
            "2024-01-02": {"USD": 1.0956},
            "2024-01-03": {"USD": 1.0919},
        },
    }
    monkeypatch.setattr(
        client.requests, "get", lambda *a, **k: _FakeResponse(payload)
    )
    got = client.fetch_rates(date(2024, 1, 1), date(2024, 1, 3), ["USD"])
    assert sorted(got) == ["2024-01-02", "2024-01-03"]
    assert "2023-12-29" not in got


def test_fetch_rates_raises_after_exhausting_retries(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Bug 4: an unreachable API was swallowed and reported as an empty result,
    so a network outage was indistinguishable from "this range has no data"."""

    def boom(*args: object, **kwargs: object) -> _FakeResponse:
        raise requests.ConnectionError("network down")

    monkeypatch.setattr(client.requests, "get", boom)
    monkeypatch.setattr(client.time, "sleep", lambda _s: None)

    with pytest.raises(client.FetchError) as excinfo:
        client.fetch_rates(date(2024, 1, 1), date(2024, 1, 3), ["USD"])
    assert "network down" in str(excinfo.value)


def test_fetch_rates_does_not_sleep_after_the_final_attempt(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Bug 4: the loop slept after *every* failure including the last one, so a
    fully failing call burned BACKOFF_SECONDS * MAX_RETRIES of pure dead time
    before giving up."""
    slept: list[float] = []

    def boom(*args: object, **kwargs: object) -> _FakeResponse:
        raise requests.ConnectionError("nope")

    monkeypatch.setattr(client.requests, "get", boom)
    monkeypatch.setattr(client.time, "sleep", lambda s: slept.append(s))

    with pytest.raises(client.FetchError):
        client.fetch_rates(date(2024, 1, 1), date(2024, 1, 3), ["USD"])
    assert len(slept) == client.MAX_RETRIES - 1


def test_fetch_rates_retries_then_succeeds(monkeypatch: pytest.MonkeyPatch) -> None:
    """A transient failure is still retried and recovered from."""
    calls: list[int] = []

    def flaky(*args: object, **kwargs: object) -> _FakeResponse:
        calls.append(1)
        if len(calls) == 1:
            raise requests.ConnectionError("transient")
        return _FakeResponse({"rates": {"2024-01-02": {"USD": 1.0956}}})

    monkeypatch.setattr(client.requests, "get", flaky)
    monkeypatch.setattr(client.time, "sleep", lambda _s: None)

    got = client.fetch_rates(date(2024, 1, 1), date(2024, 1, 3), ["USD"])
    assert got == {"2024-01-02": {"USD": 1.0956}}
    assert len(calls) == 2


def test_cli_reports_a_fetch_failure_distinctly(
    monkeypatch: pytest.MonkeyPatch, tmp_path: object, capsys: pytest.CaptureFixture[str]
) -> None:
    """Bug 4, end to end: the CLI must say the fetch failed rather than claim
    the range has no data."""
    monkeypatch.setattr(
        report_module,
        "fetch_rates",
        lambda *a, **k: (_ for _ in ()).throw(client.FetchError("boom: unreachable")),
    )
    rc = cli.main(
        [
            "--start", "2024-01-01",
            "--end", "2024-01-31",
            "--currencies", "USD",
            "--db", str(tmp_path / "cli.db"),  # type: ignore[operator]
        ]
    )
    err = capsys.readouterr().err
    assert rc == 1
    assert "boom: unreachable" in err
    assert "no data" not in err
