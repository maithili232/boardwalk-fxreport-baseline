# fxreport

Small internal tool that pulls historical EUR exchange rates from the
[Frankfurter API](https://frankfurter.dev), caches them locally in SQLite, and
prints weekly averages.

No API key or account is needed — Frankfurter is a free public service backed by
European Central Bank reference rates.

## Requirements

Python 3.11 or newer.

## Install

    python -m pip install -e ".[dev]" -c constraints.txt

`constraints.txt` pins every transitive dependency, so the same command produces
the same environment on every machine. For a non-editable install:

    python -m pip install . -c constraints.txt

Either way you get an `fxreport` console script on your PATH.

## Usage

    fxreport --start 2024-01-01 --end 2024-03-31 --currencies USD,GBP,JPY

    week             USD       GBP       JPY
    ----------------------------------------
    2024-W01      1.0938    0.8640  157.0800
    ...

Options:

| Option         | Default        | Meaning                                   |
| -------------- | -------------- | ----------------------------------------- |
| `--start`      | *(required)*   | First day of the range, `YYYY-MM-DD`, inclusive. |
| `--end`        | *(required)*   | Last day of the range, `YYYY-MM-DD`, inclusive.  |
| `--currencies` | `USD,GBP`      | Comma-separated ISO codes, quoted against EUR.   |
| `--db`         | `fxreport.db`  | Path to the SQLite cache.                        |

The module form still works too:

    python -m fxreport.cli --start 2024-01-01 --end 2024-01-31

Exit codes: `0` success, `1` no data or a failed fetch, `2` bad arguments.

## Caching

Rates are cached in SQLite and rows are never re-fetched once they are final.
The cache records which *date ranges* have been fetched for each currency, not
just which currencies it has seen, because weekends and public holidays have no
rate at all and are indistinguishable from a gap otherwise. Re-running the same
command therefore makes no network call.

Recorded coverage stops at yesterday, so a range that runs up to today is
re-fetched next time — the current day's rate may not have been published when
you first asked. Delete the `.db` file to force a full refresh.

## Development

    python -m pip install -e ".[dev]" -c constraints.txt

    ruff check .          # lint
    ruff format .         # format
    mypy                  # strict type check
    pytest                # tests

All four run in CI on Python 3.11 and 3.12 for every pull request and every push
to `main`.

To change a dependency, edit the pin in `pyproject.toml` and regenerate the
constraints:

    python -m pip install -e ".[dev]"
    python -m pip freeze --exclude-editable | sort > constraints.txt

## Releasing

Bump `__version__` in `fxreport/__init__.py` (the packaging metadata reads it),
then push an annotated `vX.Y.Z` tag. The release workflow builds the sdist and
wheel and attaches both to the GitHub Release for that tag.

## Reports

`reports/` holds committed output from real runs, e.g. `reports/2024-Q1.txt`.
