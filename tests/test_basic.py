import pathlib
from datetime import date

from fxreport.cache import RateCache
from fxreport.cli import parse_args
from fxreport.report import iso_week_key, render, weekly_averages


def test_parse_args_defaults() -> None:
    args = parse_args(["--start", "2024-01-01", "--end", "2024-01-31"])
    assert args.currencies == "USD,GBP"
    assert args.db == "fxreport.db"


def test_iso_week_key() -> None:
    assert iso_week_key(date(2024, 1, 1)) == "2024-W01"
    assert iso_week_key(date(2023, 12, 31)) == "2023-W52"


def test_cache_roundtrip(tmp_path: pathlib.Path) -> None:
    cache = RateCache(str(tmp_path / "t.db"))
    stored = cache.store({"2024-01-02": {"USD": 1.1, "GBP": 0.9}})
    assert stored == 2
    assert cache.has_currency("USD")
    loaded = cache.load(date(2024, 1, 1), date(2024, 1, 3), ["USD", "GBP"])
    assert loaded == {"2024-01-02": {"USD": 1.1, "GBP": 0.9}}
    cache.close()


def test_weekly_averages_single_week() -> None:
    rates = {
        "2024-01-02": {"USD": 1.10},
        "2024-01-03": {"USD": 1.10},
    }
    weekly = weekly_averages(rates, ["USD"])
    assert list(weekly) == ["2024-W01"]
    assert abs(weekly["2024-W01"]["USD"] - 1.10) < 1e-9


def test_render_has_header() -> None:
    out = render(weekly_averages({"2024-01-02": {"USD": 1.1}}, ["USD"]), ["USD"])
    assert out.splitlines()[0].startswith("week")
    assert "USD" in out
