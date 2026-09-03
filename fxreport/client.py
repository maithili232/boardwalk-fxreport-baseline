"""HTTP client for the Frankfurter API (https://frankfurter.dev)."""

import time
from collections.abc import Iterable
from datetime import date

import requests

BASE_URL = "https://api.frankfurter.dev/v1"
MAX_RETRIES = 3
BACKOFF_SECONDS = 0.5


class RateFetchError(RuntimeError):
    """Raised when the Frankfurter API cannot be reached after retries."""


def fetch_rates(
    start: date, end: date, currencies: Iterable[str]
) -> dict[str, dict[str, float]]:
    """Fetch daily EUR rates for the inclusive range [start, end].

    Returns a mapping of ISO date string -> {currency: rate}.
    """
    symbols = ",".join(sorted(set(c.upper() for c in currencies)))
    url = f"{BASE_URL}/{start.isoformat()}..{end.isoformat()}"
    params = {"base": "EUR", "symbols": symbols}

    for attempt in range(MAX_RETRIES):
        try:
            resp = requests.get(url, params=params, timeout=10)
            resp.raise_for_status()
            payload = resp.json()
            if not isinstance(payload, dict):
                raise RateFetchError("the Frankfurter API returned invalid data")
            raw_rates = payload.get("rates")
            if not isinstance(raw_rates, dict):
                raise RateFetchError("the Frankfurter API returned invalid data")

            rates: dict[str, dict[str, float]] = {}
            for day, by_currency in raw_rates.items():
                if not isinstance(day, str) or not isinstance(by_currency, dict):
                    raise RateFetchError("the Frankfurter API returned invalid data")
                parsed: dict[str, float] = {}
                for currency, rate in by_currency.items():
                    if (
                        not isinstance(currency, str)
                        or not isinstance(rate, (int, float))
                        or isinstance(rate, bool)
                    ):
                        raise RateFetchError(
                            "the Frankfurter API returned invalid data"
                        )
                    parsed[currency] = float(rate)
                rates[day] = parsed
            return rates
        except requests.RequestException as error:
            if attempt == MAX_RETRIES - 1:
                raise RateFetchError(
                    "could not retrieve rates from the Frankfurter API"
                ) from error
            time.sleep(BACKOFF_SECONDS * (attempt + 1))

    raise AssertionError("retry loop completed unexpectedly")
