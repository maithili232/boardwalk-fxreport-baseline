"""Regression tests.

Each test here pins down a bug that was present in fxreport 0.3.1. Every one of
them fails against the original code and passes after the corresponding fix.
"""

import pathlib
import sqlite3
import time
from collections.abc import Iterable, Mapping
from datetime import date, timedelta

import pytest
import requests
from fxreport import cli, client
from fxreport import report as report_module
from fxreport.cache import RateCache
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
    def __init__(self, payload: Mapping[str, object], status: int = 200) -> None:
        self._payload: Mapping[str, object] = payload
        self.status_code = status

    def raise_for_status(self) -> None:
        if self.status_code >= 400:
            raise requests.HTTPError(f"{self.status_code} error")

    def json(self) -> Mapping[str, object]:
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
    monkeypatch.setattr(requests, "get", lambda *a, **k: _FakeResponse(payload))
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

    monkeypatch.setattr(requests, "get", boom)
    monkeypatch.setattr(time, "sleep", lambda _s: None)

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

    monkeypatch.setattr(requests, "get", boom)
    monkeypatch.setattr(time, "sleep", lambda s: slept.append(s))

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

    monkeypatch.setattr(requests, "get", flaky)
    monkeypatch.setattr(time, "sleep", lambda _s: None)

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
            "--start",
            "2024-01-01",
            "--end",
            "2024-01-31",
            "--currencies",
            "USD",
            "--db",
            str(tmp_path / "cli.db"),  # type: ignore[operator]
        ]
    )
    err = capsys.readouterr().err
    assert rc == 1
    assert "boom: unreachable" in err
    assert "no data" not in err


def test_uncached_range_is_fetched_even_when_currency_is_known(
    monkeypatch: pytest.MonkeyPatch, tmp_path: pathlib.Path
) -> None:
    """Bug 5: get_rates() treated "we hold at least one row for USD" as a cache
    hit, so once January had been fetched, asking for March returned whatever
    the cache happened to hold for March -- nothing -- and the CLI printed
    "no data for the requested range" without ever calling the API."""
    cache = RateCache(str(tmp_path / "c.db"))
    calls: list[tuple[date, date]] = []

    def fake_fetch(
        start: date, end: date, currencies: Iterable[str]
    ) -> dict[str, dict[str, float]]:
        calls.append((start, end))
        if start.month == 1:
            return {"2024-01-02": {"USD": 1.0956}}
        return {"2024-03-04": {"USD": 1.0857}}

    monkeypatch.setattr(report_module, "fetch_rates", fake_fetch)

    jan = report_module.get_rates(cache, date(2024, 1, 1), date(2024, 1, 31), ["USD"])
    assert jan == {"2024-01-02": {"USD": 1.0956}}

    mar = report_module.get_rates(cache, date(2024, 3, 1), date(2024, 3, 31), ["USD"])
    assert mar == {"2024-03-04": {"USD": 1.0857}}, "March must be fetched, not assumed cached"
    assert len(calls) == 2
    cache.close()


def test_repeat_request_is_served_from_cache(
    monkeypatch: pytest.MonkeyPatch, tmp_path: pathlib.Path
) -> None:
    """The flip side of bug 5: an identical repeat request must not hit the
    network again, including over weekends and holidays that legitimately have
    no rate rows of their own."""
    cache = RateCache(str(tmp_path / "c.db"))
    calls: list[tuple[date, date]] = []

    def fake_fetch(
        start: date, end: date, currencies: Iterable[str]
    ) -> dict[str, dict[str, float]]:
        calls.append((start, end))
        return {"2024-01-02": {"USD": 1.0956}, "2024-01-03": {"USD": 1.0919}}

    monkeypatch.setattr(report_module, "fetch_rates", fake_fetch)

    first = report_module.get_rates(cache, date(2024, 1, 1), date(2024, 1, 7), ["USD"])
    second = report_module.get_rates(cache, date(2024, 1, 1), date(2024, 1, 7), ["USD"])
    assert first == second
    assert len(calls) == 1, "second identical call must be served from the cache"

    # A sub-range of an already fetched window is covered too.
    report_module.get_rates(cache, date(2024, 1, 2), date(2024, 1, 5), ["USD"])
    assert len(calls) == 1

    # Adding a currency that was never fetched must trigger a fetch.
    report_module.get_rates(cache, date(2024, 1, 1), date(2024, 1, 7), ["USD", "GBP"])
    assert len(calls) == 2
    cache.close()


def test_coverage_does_not_extend_past_yesterday(tmp_path: pathlib.Path) -> None:
    """A range running up to today must stay refetchable: today's rate may not
    have been published yet when we first asked."""
    cache = RateCache(str(tmp_path / "c.db"))
    today = date.today()
    start = today - timedelta(days=10)

    cache.record_coverage("USD", start, today)
    assert cache.covers("USD", start, today - timedelta(days=1))
    assert not cache.covers("USD", start, today)
    cache.close()


def test_coverage_merges_adjacent_ranges(tmp_path: pathlib.Path) -> None:
    """Two back-to-back fetches cover the union of their ranges."""
    cache = RateCache(str(tmp_path / "c.db"))
    cache.record_coverage("USD", date(2024, 1, 1), date(2024, 1, 31))
    cache.record_coverage("USD", date(2024, 2, 1), date(2024, 2, 29))
    assert cache.covered_ranges("USD") == [(date(2024, 1, 1), date(2024, 2, 29))]
    assert cache.covers("USD", date(2024, 1, 15), date(2024, 2, 15))
    assert not cache.covers("USD", date(2024, 1, 15), date(2024, 3, 15))
    cache.close()


def test_cache_opens_a_legacy_database(tmp_path: pathlib.Path) -> None:
    """Databases written by 0.3.1 have no coverage table; opening one must add
    it rather than fail, and the old rows stay readable."""
    db = tmp_path / "legacy.db"
    conn = sqlite3.connect(str(db))
    conn.executescript(
        "CREATE TABLE rates (day TEXT NOT NULL, currency TEXT NOT NULL, "
        "rate REAL NOT NULL, PRIMARY KEY (day, currency));"
        "INSERT INTO rates VALUES ('2024-01-02', 'USD', 1.0956);"
    )
    conn.commit()
    conn.close()

    cache = RateCache(str(db))
    assert cache.load(date(2024, 1, 1), date(2024, 1, 3), ["USD"]) == {
        "2024-01-02": {"USD": 1.0956}
    }
    assert not cache.covers("USD", date(2024, 1, 1), date(2024, 1, 3))
    cache.close()
