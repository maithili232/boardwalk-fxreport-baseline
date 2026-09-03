from datetime import date
from pathlib import Path
from unittest.mock import patch

from fxreport.cache import RateCache
from fxreport.cli import parse_args
from fxreport.report import date_range, get_rates, iso_week_key, render, weekly_averages


def test_parse_args_defaults() -> None:
    args = parse_args(["--start", "2024-01-01", "--end", "2024-01-31"])
    assert args.currencies == "USD,GBP"
    assert args.db == "fxreport.db"


def test_iso_week_key() -> None:
    assert iso_week_key(date(2024, 1, 1)) == "2024-W01"
    assert iso_week_key(date(2023, 12, 31)) == "2023-W52"


def test_date_range_includes_both_endpoints() -> None:
    assert date_range(date(2024, 1, 1), date(2024, 1, 3)) == [
        date(2024, 1, 1),
        date(2024, 1, 2),
        date(2024, 1, 3),
    ]
    assert date_range(date(2024, 1, 1), date(2024, 1, 1)) == [date(2024, 1, 1)]


def test_cache_roundtrip(tmp_path: Path) -> None:
    cache = RateCache(str(tmp_path / "t.db"))
    stored = cache.store({"2024-01-02": {"USD": 1.1, "GBP": 0.9}})
    assert stored == 2
    assert cache.has_currency("USD")
    loaded = cache.load(date(2024, 1, 1), date(2024, 1, 3), ["USD", "GBP"])
    assert loaded == {"2024-01-02": {"USD": 1.1, "GBP": 0.9}}
    cache.close()


def test_get_rates_refetches_when_currency_exists_outside_requested_range(
    tmp_path: Path,
) -> None:
    cache = RateCache(str(tmp_path / "t.db"))
    cache.store({"2024-01-02": {"USD": 1.1}})
    fetched = {"2024-02-01": {"USD": 1.2}}

    with patch("fxreport.report.fetch_rates", return_value=fetched) as fetch:
        rates = get_rates(cache, date(2024, 2, 1), date(2024, 2, 2), ["USD"])

    fetch.assert_called_once_with(date(2024, 2, 1), date(2024, 2, 2), ["USD"])
    assert rates == fetched
    cache.close()


def test_get_rates_reuses_complete_range_without_fetching_again(
    tmp_path: Path,
) -> None:
    cache = RateCache(str(tmp_path / "t.db"))
    fetched = {"2024-02-01": {"USD": 1.2}}

    with patch("fxreport.report.fetch_rates", return_value=fetched) as fetch:
        first = get_rates(cache, date(2024, 2, 1), date(2024, 2, 2), ["USD"])
        second = get_rates(cache, date(2024, 2, 1), date(2024, 2, 2), ["USD"])

    assert first == second == fetched
    fetch.assert_called_once()
    cache.close()


def test_weekly_averages_single_week() -> None:
    rates = {
        "2024-01-02": {"USD": 1.10},
        "2024-01-03": {"USD": 1.10},
    }
    weekly = weekly_averages(rates, ["USD"])
    assert list(weekly) == ["2024-W01"]
    assert abs(weekly["2024-W01"]["USD"] - 1.10) < 1e-9


def test_weekly_averages_preserve_source_precision() -> None:
    rates = {
        "2024-01-02": {"USD": 1.2341},
        "2024-01-03": {"USD": 1.2349},
    }
    weekly = weekly_averages(rates, ["USD"])
    assert abs(weekly["2024-W01"]["USD"] - 1.2345) < 1e-12


def test_render_has_header() -> None:
    out = render(weekly_averages({"2024-01-02": {"USD": 1.1}}, ["USD"]), ["USD"])
    assert out.splitlines()[0].startswith("week")
    assert "USD" in out
