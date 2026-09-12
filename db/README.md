# db/ — the PostgreSQL data bank

SQL that defines `excise_bank`: the schema, the `analytics.*` published-row
views the AI path reads, the three roles, and the reference seed data. A
PostgreSQL translation of the schema in `~/Sites/upexcise-stats-dashboard`
(`docs/data-model.md` there).

`web/`'s own store is a separate MariaDB database provisioned by
`php artisan db:provision` (`subhanraj/laravel-db-provisioner`). `db:provision`
is MariaDB-only and touches nothing here.

## Scripts

| File | What it does |
|---|---|
| `roles.sql` | Creates `excise_owner`, `excise_etl`, `excise_ro`. Reassigns `excise_bank` and its schemas (`public`, `kb`, `etl`, `analytics`) to `excise_owner`. Grants: `excise_etl` gets DML on `public.*` + `kb.*` + `etl.*`; `excise_ro` gets `SELECT` on `analytics.*` + `kb.*` only, plus `default_transaction_read_only` and the statement/lock/idle timeouts. Passwords come from `psql -v` vars (`:'owner_pw'`, `:'etl_pw'`, `:'ro_pw'`), never a literal in the file. |
| `schema.sql` | `citext` extension; the base tables (dimensions, fact tables, the shops split, reference tables); the `etl` bookkeeping tables; the `kb` tables. One `set_updated_at()` trigger function with a `BEFORE UPDATE` trigger on every table that has an `updated_at` column. The fact-table and lookup indexes. |
| `analytics_views.sql` | One `analytics.<name>` view per fact and reference table, plus `analytics.districts`. Each joins its dimensions, exposes human labels next to the join ids, and filters `deleted_at IS NULL AND published_at IS NOT NULL`. The views run with the owner's privileges, so `excise_ro` reads them without any grant on the base tables. |
| `seed_reference.sql` | `zones` (5), `divisions` (18), `districts` (all 75, mapped to division and zone), `financial_years` (FY2014-15 through FY2025-26), `license_categories`. Every `INSERT` is `ON CONFLICT DO NOTHING` on the natural key; a re-run is a no-op. |
| `kb_indexes.sql` | The `kb.*` GIN/FTS index (`kb.chunks.fts`) and the document/chunk lookup indexes. `kb.chunks.fts` and `kb.chunks.embedding` are columns from `schema.sql`; this script only adds indexes over them. |

`schema.sql`, `analytics_views.sql`, and `seed_reference.sql` each begin with
`SET ROLE excise_owner` so every object is owned by `excise_owner` and the
grants in `roles.sql` reach it. Run as a superuser, they set the role; run as
`excise_owner` directly, the `SET ROLE` is a no-op.

## Apply order

The operator runs these once as a cluster superuser, per
`OPERATOR_SETUP.md` §"Data bank":

```
roles.sql  →  schema.sql  →  analytics_views.sql  →  seed_reference.sql  →  kb_indexes.sql
```

`roles.sql` runs first because it
creates the schemas the later scripts fill and registers the default
privileges that grant `excise_ro` / `excise_etl` their access on tables created
afterward.

Every script is idempotent where PostgreSQL allows it (`IF NOT EXISTS`,
`CREATE OR REPLACE VIEW`, `ON CONFLICT DO NOTHING`), so re-running the set on an
existing `excise_bank` changes nothing.

## Roles

| Role | Rights | Used by |
|---|---|---|
| `excise_owner` | Owns the database and every schema. DDL. Not a runtime login. | migrations, run by the operator |
| `excise_etl` | `INSERT` / `UPDATE` / `DELETE` on `public.*`, `kb.*`, `etl.*`. Sequence usage. No `CREATE`. | `etl/` cron jobs (Milestone 3+) |
| `excise_ro` | `SELECT` on `analytics.*` and `kb.*` only. `default_transaction_read_only = on`, `search_path = analytics, kb`, 10s statement timeout. | the orchestrator — the AI path |

`excise_ro` cannot reach the base tables (`public.*`), the ETL bookkeeping
(`etl.*`), or write anywhere, including `kb.*`. Retrieval is a read; ingestion
writes as `excise_etl`.

## Verifying

`OPERATOR_SETUP.md` §"Data bank" has the `excise_ro` read-only checks the
operator runs after applying the scripts.

For a local dry run without superuser access, apply `roles.sql` + `schema.sql` +
`analytics_views.sql` + `seed_reference.sql` in an ephemeral cluster:

```bash
export PATH=/usr/lib/postgresql/18/bin:$PATH
pg_virtualenv psql -c 'CREATE DATABASE excise_bank_scratch;'   # then apply, inspect, discard
```

`roles.sql` hardcodes `ALTER DATABASE excise_bank ...`, so a full dry run of
that file needs the database named `excise_bank`.
