"""Reporting helpers: date ranges, weekly aggregation, text rendering."""

from collections import OrderedDict
from datetime import date, timedelta
from typing import Dict, Iterable, List

from fxreport.cache import RateCache
from fxreport.client import fetch_rates


def date_range(start: date, end: date) -> List[date]:
    """All calendar days from start to end inclusive."""
    days = []
    for offset in range((end - start).days + 1):
        days.append(start + timedelta(days=offset))
    return days


def iso_week_key(day: date) -> str:
    year, week, _ = day.isocalendar()
    return "{}-W{:02d}".format(year, week)


def get_rates(cache: RateCache, start: date, end: date, currencies: Iterable[str]) -> Dict[str, Dict[str, float]]:
    """Return rates for the range, using the cache when we already have the currency."""
    currencies = [c.upper() for c in currencies]
    if all(cache.has_currency(c) for c in currencies):
        return cache.load(start, end, currencies)
    fetched = fetch_rates(start, end, currencies)
    cache.store(fetched)
    return cache.load(start, end, currencies)


def weekly_averages(rates: Dict[str, Dict[str, float]], currencies: Iterable[str]) -> "OrderedDict[str, Dict[str, float]]":
    """Average rate per ISO week per currency."""
    buckets: Dict[str, Dict[str, List[float]]] = {}
    for day_str in sorted(rates):
        day = date.fromisoformat(day_str)
        key = iso_week_key(day)
        for currency in currencies:
            rate = rates[day_str].get(currency)
            if rate is None:
                continue
            buckets.setdefault(key, {}).setdefault(currency, []).append(rate)

    result: "OrderedDict[str, Dict[str, float]]" = OrderedDict()
    for key in sorted(buckets):
        result[key] = {}
        for currency, values in buckets[key].items():
            result[key][currency] = sum(values) / len(values)
    return result


def render(weekly: "OrderedDict[str, Dict[str, float]]", currencies: Iterable[str]) -> str:
    currencies = list(currencies)
    header = "week      " + "".join("{:>10}".format(c) for c in currencies)
    lines = [header, "-" * len(header)]
    for week, by_currency in weekly.items():
        cells = "".join("{:>10.4f}".format(by_currency.get(c, float("nan"))) for c in currencies)
        lines.append("{:<10}{}".format(week, cells))
    return "\n".join(lines)
