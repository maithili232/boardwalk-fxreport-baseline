"""SQLite cache for daily rates."""

import sqlite3
from collections.abc import Iterable
from datetime import date, timedelta

SCHEMA = """
CREATE TABLE IF NOT EXISTS rates (
    day TEXT NOT NULL,
    currency TEXT NOT NULL,
    rate REAL NOT NULL,
    PRIMARY KEY (day, currency)
);

CREATE TABLE IF NOT EXISTS coverage (
    currency TEXT NOT NULL,
    start TEXT NOT NULL,
    end TEXT NOT NULL,
    PRIMARY KEY (currency, start, end)
);
"""


class RateCache:
    def __init__(self, path: str = "fxreport.db"):
        self.conn = sqlite3.connect(path)
        self.conn.executescript(SCHEMA)
        self.conn.commit()

    def close(self) -> None:
        self.conn.close()

    def has_currency(self, currency: str) -> bool:
        """True if we hold any row at all for this currency.

        Kept for backwards compatibility. This is *not* a safe cache-hit test:
        use covers() for that.
        """
        row = self.conn.execute(
            "SELECT 1 FROM rates WHERE currency = ? LIMIT 1", (currency,)
        ).fetchone()
        return row is not None

    def store(self, rates: dict[str, dict[str, float]]) -> int:
        rows = []
        for day, by_currency in rates.items():
            for currency, rate in by_currency.items():
                rows.append((day, currency, rate))
        self.conn.executemany(
            "INSERT OR REPLACE INTO rates (day, currency, rate) VALUES (?, ?, ?)", rows
        )
        self.conn.commit()
        return len(rows)

    def load(
        self, start: date, end: date, currencies: Iterable[str]
    ) -> dict[str, dict[str, float]]:
        out: dict[str, dict[str, float]] = {}
        for currency in currencies:
            cur = self.conn.execute(
                "SELECT day, rate FROM rates WHERE currency = ? "
                "AND day >= ? AND day <= ? ORDER BY day",
                (currency, start.isoformat(), end.isoformat()),
            )
            for day, rate in cur.fetchall():
                out.setdefault(day, {})[currency] = rate
        return out

    def latest_day(self, currency: str) -> str | None:
        row = self.conn.execute(
            "SELECT MAX(day) FROM rates WHERE currency = ?", (currency,)
        ).fetchone()
        return row[0] if row else None

    # -- coverage bookkeeping ------------------------------------------------
    #
    # A day with no rate is indistinguishable from a day we never asked about
    # if we only look at the `rates` table: weekends and public holidays are
    # legitimately absent. So we record which ranges have actually been
    # fetched, per currency, and consult that when deciding on a cache hit.

    def record_coverage(self, currency: str, start: date, end: date) -> None:
        """Remember that [start, end] has been fetched for `currency`.

        The end is clamped to yesterday: rates for past days are final, but
        today's rate may not have been published yet, so a range running up to
        the present must stay refetchable.
        """
        final = min(end, date.today() - timedelta(days=1))
        if final < start:
            return
        self.conn.execute(
            "INSERT OR REPLACE INTO coverage (currency, start, end) VALUES (?, ?, ?)",
            (currency, start.isoformat(), final.isoformat()),
        )
        self.conn.commit()

    def covered_ranges(self, currency: str) -> list[tuple[date, date]]:
        """Recorded ranges for `currency`, merged and sorted."""
        rows = self.conn.execute(
            "SELECT start, end FROM coverage WHERE currency = ? ORDER BY start, end",
            (currency,),
        ).fetchall()

        merged: list[tuple[date, date]] = []
        for start_str, end_str in rows:
            start, end = date.fromisoformat(start_str), date.fromisoformat(end_str)
            if merged and start <= merged[-1][1] + timedelta(days=1):
                merged[-1] = (merged[-1][0], max(merged[-1][1], end))
            else:
                merged.append((start, end))
        return merged

    def covers(self, currency: str, start: date, end: date) -> bool:
        """True if every day in [start, end] has already been fetched."""
        return any(lo <= start and end <= hi for lo, hi in self.covered_ranges(currency))
