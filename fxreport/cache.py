"""SQLite cache for daily rates."""

import sqlite3
from datetime import date
from typing import Dict, Iterable, Optional

SCHEMA = """
CREATE TABLE IF NOT EXISTS rates (
    day TEXT NOT NULL,
    currency TEXT NOT NULL,
    rate REAL NOT NULL,
    PRIMARY KEY (day, currency)
);
"""

COVERAGE_SCHEMA = """
CREATE TABLE IF NOT EXISTS rate_ranges (
    start_day TEXT NOT NULL,
    end_day TEXT NOT NULL,
    currency TEXT NOT NULL,
    PRIMARY KEY (start_day, end_day, currency)
);
"""


class RateCache:
    def __init__(self, path: str = "fxreport.db"):
        self.conn = sqlite3.connect(path)
        self.conn.execute(SCHEMA)
        self.conn.execute(COVERAGE_SCHEMA)
        self.conn.commit()

    def close(self) -> None:
        self.conn.close()

    def has_currency(self, currency: str) -> bool:
        row = self.conn.execute(
            "SELECT 1 FROM rates WHERE currency = ? LIMIT 1", (currency,)
        ).fetchone()
        return row is not None

    def store(self, rates: Dict[str, Dict[str, float]]) -> int:
        rows = []
        for day, by_currency in rates.items():
            for currency, rate in by_currency.items():
                rows.append((day, currency, rate))
        self.conn.executemany(
            "INSERT OR REPLACE INTO rates (day, currency, rate) VALUES (?, ?, ?)", rows
        )
        self.conn.commit()
        return len(rows)

    def mark_coverage(
        self, start: date, end: date, currencies: Iterable[str]
    ) -> None:
        rows = [
            (start.isoformat(), end.isoformat(), currency)
            for currency in currencies
        ]
        self.conn.executemany(
            "INSERT OR IGNORE INTO rate_ranges "
            "(start_day, end_day, currency) VALUES (?, ?, ?)",
            rows,
        )
        self.conn.commit()

    def covers(self, start: date, end: date, currency: str) -> bool:
        rows = self.conn.execute(
            "SELECT start_day, end_day FROM rate_ranges "
            "WHERE currency = ? AND end_day >= ? AND start_day <= ? "
            "ORDER BY start_day",
            (currency, start.isoformat(), end.isoformat()),
        ).fetchall()
        next_day = start
        for range_start, range_end in rows:
            covered_start = date.fromisoformat(range_start)
            covered_end = date.fromisoformat(range_end)
            if covered_start > next_day:
                return False
            if covered_end >= next_day:
                next_day = covered_end + date.resolution
            if next_day > end:
                return True
        return False

    def load(self, start: date, end: date, currencies: Iterable[str]) -> Dict[str, Dict[str, float]]:
        out: Dict[str, Dict[str, float]] = {}
        for currency in currencies:
            cur = self.conn.execute(
                "SELECT day, rate FROM rates WHERE currency = ? AND day >= ? AND day <= ? ORDER BY day",
                (currency, start.isoformat(), end.isoformat()),
            )
            for day, rate in cur.fetchall():
                out.setdefault(day, {})[currency] = rate
        return out

    def latest_day(self, currency: str) -> Optional[str]:
        row = self.conn.execute(
            "SELECT MAX(day) FROM rates WHERE currency = ?", (currency,)
        ).fetchone()
        return row[0] if row else None
