# etl/

Ingestion jobs that write the PostgreSQL data bank (`db/`). Run from cron /
systemd `--user` timers, never imported by `web/` or `orchestrator/`.
`DATA_PIPELINE.md` §ETL pipeline design covers the full picture; this is the
package layout.

```
etl/
  config.py        Settings (pydantic-settings) — DATABASE_URL_ETL, NITI_SOURCE_DIR, KB_RO_MYSQL_*
  db.py            asyncpg pool on the excise_etl role; the sync advisory lock
  normalize.py     district/FY/money/volume rules (DATA_PIPELINE.md §Normalization rules)
  loader.py        INSERT ... ON CONFLICT upsert, keyed by each table's natural key
  quarantine.py    writes a rejected row to etl.quarantine
  chunk.py         heading-aware Markdown chunking for the knowledge base
  run.py           `etl sync [--source NAME | --all]` — the sync loop and its CLI
  sources/
    base.py         RawRow — the shape every adapter yields
    csv.py          csv.DictReader over a file path
    excel.py        openpyxl over one workbook sheet
    pdf_pipeline.py pdf-markdown-pipeline (MariaDB + Markdown files) -> kb.documents / kb.chunks
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

## Knowledge base (`sources/pdf_pipeline.py`)

Reads `pdf_markdown_pipeline_local` (MariaDB, via `excise_mcp_kb_ro`) filtered
to public, verified, non-deleted documents in the Excise department, joined
for the route context (section / division / folder / rule set) that builds
each document's `docsrepo.exciseup.in` URL — mirrors
`SitemapController::documentUrl()` in that app. `fetch_documents()` (the
MariaDB read) and `sync_documents()` (hash, chunk, upsert, withdraw against
Postgres) are separate functions so the ingest logic is tested against fixture
rows with no MariaDB driver involved; `sync()` is the two glued together for
`etl sync --source pdf_pipeline_docs`.

`OPERATOR_SETUP.md` §Data bank has the one-time setup: `db/kb_indexes.sql`
applied, the `excise_mcp_kb_ro` MariaDB user created, and the
`pdf_pipeline_docs` row registered in `etl.source_registry`. After that,
`etl sync --source pdf_pipeline_docs` runs it.

## Setup

`OPERATOR_SETUP.md` §ETL package has the venv + `.env` steps.

## Tests

```bash
.venv/bin/pytest
.venv/bin/ruff check . && .venv/bin/ruff format --check .
.venv/bin/mypy .
```
