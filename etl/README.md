# etl/

Ingestion jobs that write the PostgreSQL data bank (`db/`). Run from cron /
systemd `--user` timers, never imported by `web/` or `orchestrator/`.
`DATA_PIPELINE.md` §ETL pipeline design covers the full picture; this is the
package layout.

```
etl/
  config.py        Settings (pydantic-settings) — DATABASE_URL_ETL, NITI_SOURCE_DIR
  db.py            asyncpg pool on the excise_etl role; the sync advisory lock
  normalize.py     district/FY/money/volume rules (DATA_PIPELINE.md §Normalization rules)
  loader.py        INSERT ... ON CONFLICT upsert, keyed by each table's natural key
  quarantine.py    writes a rejected row to etl.quarantine
  run.py           `etl sync [--source NAME | --all]` — the sync loop and its CLI
  sources/
    base.py        RawRow — the shape every adapter yields
    csv.py         csv.DictReader over a file path
    excel.py       openpyxl over one workbook sheet
```

## Status

The plumbing (config, db pool, advisory lock, loader, quarantine, run
bookkeeping, the csv/excel readers) is complete and tested against synthetic
fixtures. What isn't done yet: `etl/sources/excel.py`'s `SHEET_MAPS` and
`etl/run.py`'s `TABLE_NORMALIZERS` are empty — the real NITI workbook column
layout (`~/mentor_portal_db/UP Excise Data Collection/`) isn't finalized, so
there's nothing to map yet. A row for a target table with no registered
normalizer is quarantined with `reason = 'no normalizer registered for
table: ...'` rather than silently dropped, so this is visible in
`etl.ingestion_runs` once real sources are registered.

Once a workbook's layout is confirmed:

1. Add its sheet -> `(target_table, key_columns)` entry to `SHEET_MAPS`.
2. Write a `TABLE_NORMALIZERS[target_table]` function: resolve district/FY ids
   via `normalize.py`, convert money/volume, return the loader-ready dict.
3. Add the workbook as a row in `etl.source_registry`
   (`source='excel'`, `source_ref='<path>#<sheet name>'`).
4. Run `etl sync --source <name>` and check `etl.ingestion_runs` /
   `etl.quarantine` for the counts against the sibling's verified import
   (`ROADMAP.md` Milestone 1's reconciliation targets).

## Setup

`OPERATOR_SETUP.md` §ETL package has the venv + `.env` steps.

## Tests

```bash
.venv/bin/pytest
.venv/bin/ruff check . && .venv/bin/ruff format --check .
.venv/bin/mypy .
```
