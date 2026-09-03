"""Reporting helpers: date ranges, weekly aggregation, text rendering."""

from collections import OrderedDict
from collections.abc import Iterable
from datetime import date, timedelta

from fxreport.cache import RateCache
from fxreport.client import fetch_rates


def date_range(start: date, end: date) -> list[date]:
    """All calendar days from start to end inclusive."""
    days = []
    for offset in range((end - start).days + 1):
        days.append(start + timedelta(days=offset))
    return days


def iso_week_key(day: date) -> str:
    year, week, _ = day.isocalendar()
    return f"{year}-W{week:02d}"


def get_rates(
    cache: RateCache, start: date, end: date, currencies: Iterable[str]
) -> dict[str, dict[str, float]]:
    """Return rates for the range, fetching only what the cache does not cover."""
    codes = [c.upper() for c in currencies]
    if all(cache.covers(c, start, end) for c in codes):
        return cache.load(start, end, codes)

    fetched = fetch_rates(start, end, codes)
    if fetched:
        cache.store(fetched)
        for currency in codes:
            cache.record_coverage(currency, start, end)
    return cache.load(start, end, codes)


def weekly_averages(
    rates: dict[str, dict[str, float]], currencies: Iterable[str]
) -> "OrderedDict[str, dict[str, float]]":
    """Average rate per ISO week per currency."""
    buckets: dict[str, dict[str, list[float]]] = {}
    for day_str in sorted(rates):
        day = date.fromisoformat(day_str)
        key = iso_week_key(day)
        for currency in currencies:
            rate = rates[day_str].get(currency)
            if rate is None:
                continue
            buckets.setdefault(key, {}).setdefault(currency, []).append(rate)

    result: OrderedDict[str, dict[str, float]] = OrderedDict()
    for key in sorted(buckets):
        result[key] = {}
        for currency, values in buckets[key].items():
            result[key][currency] = sum(values) / len(values)
    return result


def render(weekly: "OrderedDict[str, dict[str, float]]", currencies: Iterable[str]) -> str:
    currencies = list(currencies)
    header = "week      " + "".join(f"{c:>10}" for c in currencies)
    lines = [header, "-" * len(header)]
    for week, by_currency in weekly.items():
        cells = "".join("{:>10.4f}".format(by_currency.get(c, float("nan"))) for c in currencies)
        lines.append(f"{week:<10}{cells}")
    return "\n".join(lines)
