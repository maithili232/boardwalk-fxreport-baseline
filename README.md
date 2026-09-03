# fxreport

Small internal tool that pulls historical EUR exchange rates from the
Frankfurter API, caches them locally in SQLite, and prints weekly summaries.

Written in 2021 for an internal finance spreadsheet workflow. It mostly works
but nobody has touched it in a while.

## Usage

    pip install -r requirements.txt
    python -m fxreport.cli --start 2024-01-01 --end 2024-01-31 --currencies USD,GBP

## Tests

    python -m pytest
