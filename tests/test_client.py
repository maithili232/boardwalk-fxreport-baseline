from datetime import date
from unittest.mock import patch

import pytest
import requests

from fxreport.client import RateFetchError, fetch_rates


def test_fetch_rates_raises_after_retries_are_exhausted() -> None:
    with (
        patch(
            "fxreport.client.requests.get",
            side_effect=requests.ConnectionError("offline"),
        ) as get,
        patch("fxreport.client.time.sleep") as sleep,
        pytest.raises(RateFetchError, match="could not retrieve rates"),
    ):
        fetch_rates(date(2024, 1, 1), date(2024, 1, 2), ["USD"])

    assert get.call_count == 3
    assert sleep.call_count == 2
