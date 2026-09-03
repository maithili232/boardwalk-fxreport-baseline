"""HTTP client for the Frankfurter API (https://frankfurter.dev)."""

import time
from datetime import date
from typing import Dict, Iterable

import requests

BASE_URL = "https://api.frankfurter.dev/v1"
MAX_RETRIES = 3
BACKOFF_SECONDS = 0.5


class RateFetchError(RuntimeError):
    """Raised when the Frankfurter API cannot be reached after retries."""


def fetch_rates(start: date, end: date, currencies: Iterable[str]) -> Dict[str, Dict[str, float]]:
    """Fetch daily EUR rates for the inclusive range [start, end].

    Returns a mapping of ISO date string -> {currency: rate}.
    """
    symbols = ",".join(sorted(set(c.upper() for c in currencies)))
    url = "{}/{}..{}".format(BASE_URL, start.isoformat(), end.isoformat())
    params = {"base": "EUR", "symbols": symbols}

    for attempt in range(MAX_RETRIES):
        try:
            resp = requests.get(url, params=params, timeout=10)
            resp.raise_for_status()
            payload = resp.json()
            return payload.get("rates", {})
        except requests.RequestException as error:
            if attempt == MAX_RETRIES - 1:
                raise RateFetchError(
                    "could not retrieve rates from the Frankfurter API"
                ) from error
            time.sleep(BACKOFF_SECONDS * (attempt + 1))

    raise AssertionError("retry loop completed unexpectedly")
