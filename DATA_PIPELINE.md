# DATA_PIPELINE.md — ETL ingestion and the PostgreSQL data bank

## Position

The excise data bank is a **PostgreSQL translation of the already-built,
already-verified schema in `~/Sites/upexcise-stats-dashboard`**
(`docs/data-model.md` there). That schema holds FY2014-15 onward: 75 districts,
900 rows per series on Revenue / Sales Volume / Operations, ~79,685 shops /
242,520 shop-years, 3,524 brands, 5,537 brand prices, 72 duty rates, 60 policy
rows, all reconciled against the source NITI workbooks with four import bugs
found and fixed. Do not design a new schema. Translate that one and add the
columns this project needs on top.

`web/`'s own small store (users, sessions, the query ledger, the job queue) is
a separate MariaDB database, `excise_mcp_dashboard_local`, provisioned by
`php artisan db:provision`. It is not the data bank and never holds excise
figures.

## PostgreSQL schema blueprint

MariaDB -> PostgreSQL translation rules:

- `utf8mb4` / `utf8mb4_unicode_ci` -> database `ENCODING 'UTF8'`,
  `LC_COLLATE`/`LC_CTYPE` from the cluster; add `CITEXT` for
  case-insensitive natural keys (the shop-identity collation bug in the sibling
  was a collation-prediction mistake — use `CITEXT` or explicit
  `LOWER()` functional unique indexes, and resolve identity with a real query,
  not an in-code guess).
- `AUTO_INCREMENT` -> `GENERATED ALWAYS AS IDENTITY`.
- `bigInteger unsigned` FKs -> `BIGINT` + `REFERENCES`.
- `decimal(15,2)` money -> `NUMERIC(15,2)`.
- Laravel `timestamps` -> `created_at TIMESTAMPTZ NOT NULL DEFAULT now()`,
  `updated_at TIMESTAMPTZ NOT NULL DEFAULT now()` (a trigger keeps
  `updated_at` current).
- Soft delete -> `deleted_at TIMESTAMPTZ NULL`, partial indexes
  `WHERE deleted_at IS NULL`.
- `published_at` stays — the AI only ever reads published rows (see §Row
  visibility).

### Dimensions

```sql
CREATE TABLE zones (
    id           BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    name         CITEXT NOT NULL UNIQUE,
    slug         CITEXT NOT NULL UNIQUE,
    created_at   TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at   TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE divisions (
    id           BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    zone_id      BIGINT NOT NULL REFERENCES zones(id),
    name         CITEXT NOT NULL,
    slug         CITEXT NOT NULL UNIQUE,
    created_at   TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at   TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (zone_id, name)
);

CREATE TABLE districts (
    id            BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    division_id   BIGINT NOT NULL REFERENCES divisions(id),
    name          CITEXT NOT NULL UNIQUE,
    slug          CITEXT NOT NULL UNIQUE,
    lgd_code      INTEGER UNIQUE,          -- Local Government Directory code, for joins to other gov datasets
    latitude      NUMERIC(9,6),
    longitude     NUMERIC(9,6),
    published_at  TIMESTAMPTZ NULL,
    created_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
    deleted_at    TIMESTAMPTZ NULL
);

CREATE TABLE financial_years (
    id           BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    label        TEXT NOT NULL UNIQUE,     -- 'FY2014-15'
    start_year   SMALLINT NOT NULL UNIQUE, -- 2014
    created_at   TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at   TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE license_categories (
    id           BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    code         CITEXT NOT NULL UNIQUE,   -- e.g. 'CL', 'FL', 'BEER', 'BWFL'
    name         TEXT NOT NULL,
    kind         TEXT NOT NULL,            -- 'country_liquor' | 'foreign_liquor' | 'beer' | 'model_shop' | ...
    created_at   TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at   TIMESTAMPTZ NOT NULL DEFAULT now()
);
```

### Fact tables (one per NITI series)

```sql
CREATE TABLE revenues (                    -- duty / fee collections
    id                 BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    district_id        BIGINT NOT NULL REFERENCES districts(id),
    financial_year_id  BIGINT NOT NULL REFERENCES financial_years(id),
    license_category_id BIGINT REFERENCES license_categories(id),  -- NULL = all-category total row
    metric             TEXT NOT NULL,       -- 'excise_duty' | 'license_fee' | 'import_fee' | 'total'
    amount_inr         NUMERIC(18,2) NOT NULL,   -- store in rupees, format in the UI
    published_at       TIMESTAMPTZ NULL,
    source_ref         TEXT,                -- workbook / sheet / row provenance
    created_at         TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at         TIMESTAMPTZ NOT NULL DEFAULT now(),
    deleted_at         TIMESTAMPTZ NULL,
    UNIQUE (district_id, financial_year_id, license_category_id, metric)
);

CREATE TABLE sales_volumes (               -- dispatches / supply-chain volume
    id                 BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    district_id        BIGINT NOT NULL REFERENCES districts(id),
    financial_year_id  BIGINT NOT NULL REFERENCES financial_years(id),
    license_category_id BIGINT REFERENCES license_categories(id),
    metric             TEXT NOT NULL,       -- 'dispatch_bl' | 'consumption_bl' | 'cases'
    quantity           NUMERIC(18,3) NOT NULL,
    unit               TEXT NOT NULL,       -- 'BL' (bulk litres) | 'cases'
    published_at       TIMESTAMPTZ NULL,
    source_ref         TEXT,
    created_at         TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at         TIMESTAMPTZ NOT NULL DEFAULT now(),
    deleted_at         TIMESTAMPTZ NULL,
    UNIQUE (district_id, financial_year_id, license_category_id, metric)
);

CREATE TABLE operations (                  -- enforcement statistics
    id                 BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    district_id        BIGINT NOT NULL REFERENCES districts(id),
    financial_year_id  BIGINT NOT NULL REFERENCES financial_years(id),
    metric             TEXT NOT NULL,       -- 'raids' | 'cases_registered' | 'arrests' | 'liquor_seized_bl' | 'vehicles_seized'
    value              NUMERIC(18,3) NOT NULL,
    published_at       TIMESTAMPTZ NULL,
    source_ref         TEXT,
    created_at         TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at         TIMESTAMPTZ NOT NULL DEFAULT now(),
    deleted_at         TIMESTAMPTZ NULL,
    UNIQUE (district_id, financial_year_id, metric)
);
```

### Shops (dimension + fact split, as in the sibling)

```sql
CREATE TABLE shops (
    id             BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    district_id    BIGINT NOT NULL REFERENCES districts(id),
    shop_number    CITEXT NOT NULL,
    seq            SMALLINT NOT NULL DEFAULT 1,   -- disambiguator for same district+number (see sibling data-model.md)
    display_name   TEXT NOT NULL,
    license_category_id BIGINT REFERENCES license_categories(id),
    circle_code    CITEXT,
    sector_code    CITEXT,
    latitude       NUMERIC(9,6),
    longitude      NUMERIC(9,6),
    published_at   TIMESTAMPTZ NULL,
    created_at     TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at     TIMESTAMPTZ NOT NULL DEFAULT now(),
    deleted_at     TIMESTAMPTZ NULL,
    UNIQUE (district_id, shop_number, seq)
);

CREATE TABLE shop_years (                  -- quota / settlement per shop per FY
    id                 BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    shop_id            BIGINT NOT NULL REFERENCES shops(id),
    financial_year_id  BIGINT NOT NULL REFERENCES financial_years(id),
    shop_type          TEXT NOT NULL,       -- country liquor / foreign liquor / beer / model shop / composite
    mgq_bl             NUMERIC(18,3),       -- minimum guaranteed quota
    license_fee_inr    NUMERIC(18,2),
    settlement_mode    TEXT,                -- 'lottery' | 'e-lottery' | 'renewal' | 'auction'
    is_operational     BOOLEAN,
    source_ref         TEXT,
    created_at         TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at         TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (shop_id, financial_year_id)
    -- visibility inherited from shops.published_at; shop_years has no published_at
);
```

### Reference tables

```sql
CREATE TABLE brands (
    id             BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    name           CITEXT NOT NULL,
    license_category_id BIGINT REFERENCES license_categories(id),
    segment        TEXT,                   -- 'regular' | 'premium' | 'economy'
    manufacturer   TEXT,
    published_at   TIMESTAMPTZ NULL,
    created_at     TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at     TIMESTAMPTZ NOT NULL DEFAULT now(),
    deleted_at     TIMESTAMPTZ NULL,
    UNIQUE (name, license_category_id)
);

CREATE TABLE brand_prices (
    id                 BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    brand_id           BIGINT NOT NULL REFERENCES brands(id),
    financial_year_id  BIGINT NOT NULL REFERENCES financial_years(id),
    pack_ml            INTEGER NOT NULL,
    mrp_inr            NUMERIC(12,2) NOT NULL,
    ex_distillery_inr  NUMERIC(12,2),
    published_at       TIMESTAMPTZ NULL,
    created_at         TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at         TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (brand_id, financial_year_id, pack_ml)
);

CREATE TABLE duty_rates (
    id                 BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    financial_year_id  BIGINT NOT NULL REFERENCES financial_years(id),
    license_category_id BIGINT NOT NULL REFERENCES license_categories(id),
    basis              TEXT NOT NULL,       -- 'per_bl' | 'per_lpl' | 'ad_valorem' | 'per_case'
    rate               NUMERIC(14,4) NOT NULL,
    unit               TEXT NOT NULL,
    notes              TEXT,
    published_at       TIMESTAMPTZ NULL,
    created_at         TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at         TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (financial_year_id, license_category_id, basis)
);

CREATE TABLE policy_entries (
    id             BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    financial_year_id BIGINT REFERENCES financial_years(id),
    effective_from DATE,
    effective_to   DATE,
    title          TEXT NOT NULL,
    category       TEXT,                   -- 'pricing' | 'licensing' | 'enforcement' | 'quota' | 'structural'
    summary        TEXT NOT NULL,
    source_ref     TEXT,
    published_at   TIMESTAMPTZ NULL,
    created_at     TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at     TIMESTAMPTZ NOT NULL DEFAULT now(),
    deleted_at     TIMESTAMPTZ NULL
);
```

### ETL bookkeeping (separate schema)

```sql
CREATE SCHEMA etl;

CREATE TABLE etl.ingestion_runs (
    id            BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    source        TEXT NOT NULL,           -- 'google_sheet' | 'google_drive' | 'excel' | 'csv'
    source_ref    TEXT NOT NULL,           -- sheet id / drive file id / path
    started_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
    finished_at   TIMESTAMPTZ,
    status        TEXT NOT NULL DEFAULT 'running',  -- running | ok | failed | partial
    rows_seen     INTEGER DEFAULT 0,
    rows_upserted INTEGER DEFAULT 0,
    rows_quarantined INTEGER DEFAULT 0,
    error         TEXT
);

CREATE TABLE etl.quarantine (
    id            BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    run_id        BIGINT NOT NULL REFERENCES etl.ingestion_runs(id),
    raw_row       JSONB NOT NULL,
    reason        TEXT NOT NULL,
    created_at    TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE etl.source_registry (        -- what to sync and how often
    id            BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    name          TEXT NOT NULL UNIQUE,
    source        TEXT NOT NULL,
    source_ref    TEXT NOT NULL,
    target_table  TEXT NOT NULL,
    schedule      TEXT NOT NULL,           -- cron expression
    enabled       BOOLEAN NOT NULL DEFAULT true,
    last_run_id   BIGINT REFERENCES etl.ingestion_runs(id)
);
```

### Indexes

Every fact table: `(financial_year_id)`, `(district_id, financial_year_id)`,
`(metric)` where present, and a partial `(published_at) WHERE published_at IS
NOT NULL`. `shop_years (financial_year_id, shop_type)`. `brand_prices
(financial_year_id)`. Add from the actual query plans the LLM produces — the
ledger records every SQL statement, so index tuning is driven by real usage
after Milestone 2.

### Row visibility for the AI path

The read-only role sees a set of views, not the base tables:

```sql
CREATE SCHEMA analytics;
CREATE VIEW analytics.revenues AS
    SELECT r.*, d.name AS district, d.slug AS district_slug,
           fy.label AS financial_year, fy.start_year,
           lc.code AS license_category
    FROM revenues r
    JOIN districts d  ON d.id = r.district_id AND d.deleted_at IS NULL AND d.published_at IS NOT NULL
    JOIN financial_years fy ON fy.id = r.financial_year_id
    LEFT JOIN license_categories lc ON lc.id = r.license_category_id
    WHERE r.deleted_at IS NULL AND r.published_at IS NOT NULL;
-- one such view per fact + reference table; shop_years joins shops for published_at
```

The LLM is told about `analytics.*` only. It never learns the base table names,
the `id` columns are still present for joins but the natural-language layer
works in district names and FY labels. `SECURITY.md` §Read-only role grants
`SELECT` on `analytics.*` and nothing else.

## ETL pipeline design

`etl/` is a small Python 3.12 package run from cron / systemd timers. One
command, `etl sync [--source NAME] [--all]`, reads `etl.source_registry`,
runs each due source through: **fetch -> normalize -> validate -> upsert ->
record run**.

### Shared shape

Every source adapter yields rows in one normalized dict shape per target
table (the loader knows the natural key per table and does `INSERT ... ON
CONFLICT ... DO UPDATE`). A row that fails validation (missing natural-key
field, unparseable number, unknown district) goes to `etl.quarantine` with a
reason and is counted, never inserted. A run writes one
`etl.ingestion_runs` row with counts; a non-zero quarantine count sets status
`partial` and the run summary is logged and (optionally) mailed.

Idempotent by construction: re-running the same source over the same
unchanged input upserts identical values and changes no counts. This is the
property the sibling `excise:import` already has and the tests enforce.

### Source adapters

**Google Sheets** (`etl/sources/gsheets.py`)
- Auth: a Google Cloud **service account**; the JSON key file path comes from
  `GOOGLE_APPLICATION_CREDENTIALS` (env), never committed, `600` perms. The
  target sheets are shared with the service account's email as Viewer.
- Library: `google-api-python-client` + `google-auth` (read-only scope
  `https://www.googleapis.com/auth/spreadsheets.readonly`).
- Reads a named range or a whole tab; the `source_registry` row carries the
  sheet id, the tab/range, and the target table. A per-sheet column map
  (`etl/maps/<sheet>.yml`) translates sheet headers to normalized fields.
- Change detection: the Sheets API returns a `revisionId` / the Drive API a
  `modifiedTime`; skip a source whose `modifiedTime` is not newer than the
  last successful run unless `--force`.

**Google Drive** (`etl/sources/gdrive.py`)
- Same service account, scope `.../auth/drive.readonly`.
- Lists a folder, downloads new/changed `.xlsx` / `.csv` files to a temp dir,
  then hands each to the Excel or CSV adapter. Native Google Sheets files in
  the folder are exported as `.xlsx` via `files().export`.
- Dedup on Drive `fileId` + `md5Checksum`.

**Excel** (`etl/sources/excel.py`)
- Library: `openpyxl` for `.xlsx`; `.xls` is rare — convert with LibreOffice
  headless (`soffice --headless --convert-to xlsx`) only if a real `.xls`
  appears, otherwise do not add the dependency.
- Mirrors the sibling `ImportExciseData` logic: the note-row filter that once
  truncated sheets is replaced by an explicit "this row is data if the
  natural-key columns are all present and numeric" test, not a heuristic on
  column A length.
- One workbook can feed several tables (the NITI submission workbooks do);
  the column map names the target per sheet.

**CSV / local & network shares** (`etl/sources/csv.py`)
- `csv` stdlib + explicit `dialect`; declared encoding in the registry row
  (default `utf-8-sig`).
- A registry row can point at a directory glob on a mounted share; each file
  is one logical source keyed by path + mtime + size.

### Normalization rules

- Districts resolve by `CITEXT` name against `districts`; an unrecognized name
  is quarantined with `reason = 'unknown district: <value>'` (a small alias
  table `etl.district_aliases(alias CITEXT, district_id)` handles known
  spelling variants — seed it from the sibling's cleanup notes).
- Financial years parse from any of `2014-15`, `FY2014-15`, `2014_15`,
  `2014` -> `financial_years.start_year`.
- Money: strip `₹`, commas, spaces; reject anything left non-numeric; store
  rupees (not lakh/crore) — the registry row says the input unit and the
  adapter multiplies.
- Volumes: normalize to bulk litres (`BL`); cases stay as `cases` in their own
  metric.
- Every inserted row carries `source_ref = '<run source>:<source_ref>:<row
  number>'` so a figure in the UI can be traced to a cell.

### Schedules

Driven by `etl.source_registry.schedule` (cron expressions), executed by
systemd `--user` timers generated in `deploy/`:

| Source class | Default cadence | Rationale |
|---|---|---|
| Google Sheets (live working sheets) | every 6 h, `0 */6 * * *` | analysts edit these during the day; 6 h keeps the bank fresh without hammering the API |
| Google Drive folder (dropped workbooks) | hourly, `15 * * * *` | pick up a new submission workbook soon after it lands |
| Local / network-share CSV | daily 02:30, `30 2 * * *` | batch exports, updated overnight |
| Full NITI workbook re-import | manual (`etl sync --source niti_full`) | the annual reconciled set; run on demand, verify counts like the sibling did |

All timers are `--user` units with `Persistent=true` so a missed run (box
off) fires on next boot. A run acquires a Postgres advisory lock
(`pg_try_advisory_lock`) so overlapping timers cannot double-load.

### Failure and alerting

- A source that fails leaves its last-good data in place (upsert-only, no
  truncate-then-load).
- `etl.ingestion_runs.status = 'failed'` with the exception in `error`.
- The run command exits non-zero; the systemd unit's `OnFailure=` points at a
  small notifier unit that mails the run summary through the same Resend setup
  the Laravel apps use (`MAIL_MAILER=resend`, `noreply@mail.exciseup.in`).
- `partial` (quarantined rows) mails a lower-priority digest, not a failure.

### What the ETL never does

- No writes from the web path — `etl/` is cron-only, not importable by `web/`
  or `orchestrator/`.
- No schema changes after the initial migration — the ETL role has
  `INSERT`/`UPDATE`/`DELETE` on data tables and `etl.*`, no `CREATE`/`ALTER`.
- No deletes of published history except through an explicit
  `etl sync --source X --reconcile` run that logs every delete to
  `etl.quarantine` first.
