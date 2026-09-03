"""HTTP client for the Frankfurter API (https://frankfurter.dev)."""

import time
from collections.abc import Iterable
from datetime import date

import requests

BASE_URL = "https://api.frankfurter.dev/v1"
MAX_RETRIES = 3
BACKOFF_SECONDS = 0.5


class FetchError(RuntimeError):
    """Raised when the Frankfurter API could not be reached or understood."""


def fetch_rates(start: date, end: date, currencies: Iterable[str]) -> dict[str, dict[str, float]]:
    """Fetch daily EUR rates for the inclusive range [start, end].

    Returns a mapping of ISO date string -> {currency: rate}.
    """
    symbols = ",".join(sorted({c.upper() for c in currencies}))
    url = f"{BASE_URL}/{start.isoformat()}..{end.isoformat()}"
    params = {"base": "EUR", "symbols": symbols}

    last_error: Exception | None = None
    for attempt in range(MAX_RETRIES):
        try:
            resp = requests.get(url, params=params, timeout=10)
            resp.raise_for_status()
            payload = resp.json()
            return _within_range(payload.get("rates", {}), start, end)
        except (requests.RequestException, ValueError) as exc:
            last_error = exc
            if attempt == MAX_RETRIES - 1:
                break
            time.sleep(BACKOFF_SECONDS * (attempt + 1))

    raise FetchError(
        f"could not fetch rates for {start.isoformat()}..{end.isoformat()} "
        f"after {MAX_RETRIES} attempts: {last_error}"
    ) from last_error


def _within_range(
    rates: dict[str, dict[str, float]], start: date, end: date
) -> dict[str, dict[str, float]]:
    """Drop any day the API returned that falls outside [start, end].

    Frankfurter widens a range request backwards to the closest preceding
    business day, so a query starting on a weekend or a holiday comes back
    with an extra day in front of the requested window.
    """
    lo, hi = start.isoformat(), end.isoformat()
    return {day: by_currency for day, by_currency in rates.items() if lo <= day <= hi}
