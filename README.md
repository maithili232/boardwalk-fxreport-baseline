# fxreport

`fxreport` pulls historical EUR exchange rates from the public Frankfurter API,
caches successful date ranges in SQLite, and prints weekly averages.

Python 3.11 or newer is required.

## Install

Install the published wheel or the current source tree:

```console
python -m pip install .
fxreport --version
```

For development, create a virtual environment and install the project in
editable mode with the fully pinned development dependencies:

```console
python -m venv .venv
.venv/Scripts/python -m pip install --constraint requirements.lock pip==26.2.1
.venv/Scripts/python -m pip install --constraint requirements.lock -e ".[dev]"
```

On macOS or Linux, use `.venv/bin/python` instead.

## Usage

```console
fxreport --start 2024-01-01 --end 2024-01-31 --currencies USD,GBP
```

The default cache is `fxreport.db`. Choose another location with `--db`:

```console
fxreport --start 2024-01-01 --end 2024-01-31 \
  --currencies USD,GBP,JPY --db reports/rates.db
```

All ranges are inclusive. Once a requested range and currency are cached, the
same request is served without an API call.

## Quality checks

```console
.venv/Scripts/ruff check .
.venv/Scripts/ruff format --check .
.venv/Scripts/mypy
.venv/Scripts/python -m pytest
```

Run the equivalent executables under `.venv/bin` on macOS or Linux. To refresh
the lock file after intentionally changing an exact dependency pin, run:

```console
.venv/Scripts/pip-compile --all-extras --allow-unsafe --strip-extras \
  --output-file requirements.lock pyproject.toml
```
