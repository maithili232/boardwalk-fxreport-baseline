"""Command-line entry point."""

import argparse
import sys
from datetime import date

from fxreport import __version__
from fxreport.cache import RateCache
from fxreport.report import get_rates, render, weekly_averages


def parse_args(argv=None):
    p = argparse.ArgumentParser(prog="fxreport", description="Weekly EUR exchange rate summaries")
    p.add_argument("--start", required=True, help="start date YYYY-MM-DD (inclusive)")
    p.add_argument("--end", required=True, help="end date YYYY-MM-DD (inclusive)")
    p.add_argument("--currencies", default="USD,GBP", help="comma separated currency codes")
    p.add_argument("--db", default="fxreport.db", help="path to sqlite cache")
    p.add_argument("--version", action="version", version="fxreport {}".format(__version__))
    return p.parse_args(argv)


def main(argv=None) -> int:
    args = parse_args(argv)
    start = date.fromisoformat(args.start)
    end = date.fromisoformat(args.end)
    if end < start:
        print("error: --end must not be before --start", file=sys.stderr)
        return 2
    currencies = [c.strip().upper() for c in args.currencies.split(",") if c.strip()]

    cache = RateCache(args.db)
    try:
        rates = get_rates(cache, start, end, currencies)
    finally:
        cache.close()

    if not rates:
        print("no data for the requested range", file=sys.stderr)
        return 1

    weekly = weekly_averages(rates, currencies)
    print(render(weekly, currencies))
    return 0


if __name__ == "__main__":
    sys.exit(main())
