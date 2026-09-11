-- schema.sql — the excise_bank data bank: base tables, etl bookkeeping, and the
-- kb schema. A PostgreSQL translation of the schema in
-- ~/Sites/upexcise-stats-dashboard (docs/data-model.md there).
--
-- Apply after roles.sql, as a superuser:
--   sudo -u postgres psql -d excise_bank -f schema.sql
--
-- analytics.* views: analytics_views.sql. kb.* FTS/GIN indexes: kb_indexes.sql
-- (Milestone 3). Reference seed data: seed_reference.sql.

\set ON_ERROR_STOP on

CREATE EXTENSION IF NOT EXISTS citext;

-- Own every object created below as excise_owner so the ALTER DEFAULT PRIVILEGES
-- in roles.sql grant excise_etl / excise_ro their access automatically. A no-op
-- when the script is already connected as excise_owner.
SET ROLE excise_owner;

CREATE SCHEMA IF NOT EXISTS etl;
CREATE SCHEMA IF NOT EXISTS kb;
CREATE SCHEMA IF NOT EXISTS analytics;

-- updated_at maintenance: one function, applied by trigger to every public table
-- that carries an updated_at column (the DO block at the end of this file).
CREATE OR REPLACE FUNCTION set_updated_at() RETURNS trigger
LANGUAGE plpgsql AS $$
BEGIN
    NEW.updated_at := now();
    RETURN NEW;
END;
$$;

-- ---------------------------------------------------------------------------
-- Dimensions
-- ---------------------------------------------------------------------------

CREATE TABLE IF NOT EXISTS zones (
    id           BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    name         CITEXT NOT NULL UNIQUE,
    slug         CITEXT NOT NULL UNIQUE,
    created_at   TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at   TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS divisions (
    id           BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    zone_id      BIGINT NOT NULL REFERENCES zones(id),
    name         CITEXT NOT NULL,
    slug         CITEXT NOT NULL UNIQUE,
    created_at   TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at   TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (zone_id, name)
);

CREATE TABLE IF NOT EXISTS districts (
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

CREATE TABLE IF NOT EXISTS financial_years (
    id           BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    label        TEXT NOT NULL UNIQUE,     -- 'FY2014-15'
    start_year   SMALLINT NOT NULL UNIQUE, -- 2014
    created_at   TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at   TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS license_categories (
    id           BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    code         CITEXT NOT NULL UNIQUE,   -- 'CL', 'FL', 'BEER', 'BWFL', ...
    name         TEXT NOT NULL,
    kind         TEXT NOT NULL,            -- 'country_liquor' | 'foreign_liquor' | 'beer' | 'model_shop' | ...
    created_at   TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at   TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- ---------------------------------------------------------------------------
-- Fact tables (one per NITI series)
-- ---------------------------------------------------------------------------

CREATE TABLE IF NOT EXISTS revenues (                    -- duty / fee collections
    id                 BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    district_id        BIGINT NOT NULL REFERENCES districts(id),
    financial_year_id  BIGINT NOT NULL REFERENCES financial_years(id),
    license_category_id BIGINT REFERENCES license_categories(id),  -- NULL = all-category total row
    metric             TEXT NOT NULL,       -- 'excise_duty' | 'license_fee' | 'import_fee' | 'total'
    amount_inr         NUMERIC(18,2) NOT NULL,   -- rupees; formatted in the UI
    published_at       TIMESTAMPTZ NULL,
    source_ref         TEXT,                -- workbook / sheet / row provenance
    created_at         TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at         TIMESTAMPTZ NOT NULL DEFAULT now(),
    deleted_at         TIMESTAMPTZ NULL,
    UNIQUE (district_id, financial_year_id, license_category_id, metric)
);

CREATE TABLE IF NOT EXISTS sales_volumes (               -- dispatches / supply-chain volume
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

CREATE TABLE IF NOT EXISTS operations (                  -- enforcement statistics
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

-- ---------------------------------------------------------------------------
-- Shops (dimension + fact split)
-- ---------------------------------------------------------------------------

CREATE TABLE IF NOT EXISTS shops (
    id             BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    district_id    BIGINT NOT NULL REFERENCES districts(id),
    shop_number    CITEXT NOT NULL,
    seq            SMALLINT NOT NULL DEFAULT 1,   -- disambiguator for same district + number (sibling data-model.md)
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

CREATE TABLE IF NOT EXISTS shop_years (                  -- quota / settlement per shop per FY
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

-- ---------------------------------------------------------------------------
-- Reference tables
-- ---------------------------------------------------------------------------

CREATE TABLE IF NOT EXISTS brands (
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

CREATE TABLE IF NOT EXISTS brand_prices (
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

CREATE TABLE IF NOT EXISTS duty_rates (
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

CREATE TABLE IF NOT EXISTS policy_entries (
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
    deleted_at     TIMESTAMPTZ NULL,
    UNIQUE (source_ref)  -- policy text has no other stable natural key; the loader upserts on this
);

-- ---------------------------------------------------------------------------
-- ETL bookkeeping
-- ---------------------------------------------------------------------------

CREATE TABLE IF NOT EXISTS etl.ingestion_runs (
    id            BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    source        TEXT NOT NULL,           -- 'google_sheet' | 'google_drive' | 'excel' | 'csv' | 'pdf_pipeline' | 'upload'
    source_ref    TEXT NOT NULL,           -- sheet id / drive file id / path
    started_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
    finished_at   TIMESTAMPTZ,
    status        TEXT NOT NULL DEFAULT 'running',  -- running | ok | failed | partial
    rows_seen     INTEGER DEFAULT 0,
    rows_upserted INTEGER DEFAULT 0,
    rows_quarantined INTEGER DEFAULT 0,
    error         TEXT
);

CREATE TABLE IF NOT EXISTS etl.quarantine (
    id            BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    run_id        BIGINT NOT NULL REFERENCES etl.ingestion_runs(id),
    raw_row       JSONB NOT NULL,
    reason        TEXT NOT NULL,
    created_at    TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS etl.source_registry (        -- what to sync and how often
    id            BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    name          TEXT NOT NULL UNIQUE,
    source        TEXT NOT NULL,
    source_ref    TEXT NOT NULL,
    target_table  TEXT NOT NULL,
    schedule      TEXT NOT NULL,           -- cron expression
    enabled       BOOLEAN NOT NULL DEFAULT true,
    last_run_id   BIGINT REFERENCES etl.ingestion_runs(id)
);

CREATE TABLE IF NOT EXISTS etl.district_aliases (  -- known spelling variants, seeded as they turn up
    alias         CITEXT NOT NULL PRIMARY KEY,
    district_id   BIGINT NOT NULL REFERENCES districts(id)
);

-- ---------------------------------------------------------------------------
-- Knowledge base (kb schema)
-- ---------------------------------------------------------------------------
-- Tables only. The GIN FTS index and the document/chunk indexes are in
-- kb_indexes.sql, added at Milestone 3.

CREATE TABLE IF NOT EXISTS kb.documents (
    id             BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    origin         TEXT NOT NULL,           -- 'pdf_pipeline' | 'upload' | 'gdoc' | 'gdrive'
    origin_ref     TEXT NOT NULL,           -- pipeline document id | upload ulid | gdoc id | drive fileId
    title          TEXT NOT NULL,
    doc_type       TEXT,                    -- 'act' | 'rule' | 'rule_amendment' | 'policy' | 'government_order' | 'notice' | 'court_order' | 'service_code' | 'other'
    language       TEXT,                    -- 'english' | 'hindi' | 'both'
    department     TEXT,                    -- 'excise' | 'sugarcane' | ...
    rule_set       TEXT,                    -- named Act / Rules / policy series, when known
    effective_from DATE,
    effective_to   DATE,                    -- set when a later doc supersedes this one
    source_url     TEXT,                    -- deep link on docsrepo.exciseup.in, or the Drive/Docs URL
    content_sha256 TEXT NOT NULL,           -- of the full Markdown, for change detection
    ingested_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
    withdrawn_at   TIMESTAMPTZ NULL,        -- upstream doc went non-public / unverified / deleted, or upload withdrawn
    UNIQUE (origin, origin_ref)
);

CREATE TABLE IF NOT EXISTS kb.chunks (
    id             BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    document_id    BIGINT NOT NULL REFERENCES kb.documents(id) ON DELETE CASCADE,
    ord            INTEGER NOT NULL,        -- chunk order within the document
    heading_path   TEXT,                    -- 'Chapter III > Section 12 > (2)' for citation
    content        TEXT NOT NULL,           -- the chunk text, Markdown
    token_estimate INTEGER NOT NULL,
    fts            tsvector GENERATED ALWAYS AS (
                       to_tsvector('simple', coalesce(heading_path, '') || ' ' || content)
                   ) STORED,
    embedding      real[] NULL,             -- populated only when KB_EMBEDDINGS_ENABLED; becomes vector(N) with pgvector
    UNIQUE (document_id, ord)
);

-- ---------------------------------------------------------------------------
-- Indexes (public schema). kb.* indexes live in kb_indexes.sql (Milestone 3).
-- Further indexes come from real query plans after Milestone 2 — the ledger
-- records every statement the LLM runs.
-- ---------------------------------------------------------------------------

CREATE INDEX IF NOT EXISTS revenues_fy_idx          ON revenues (financial_year_id) WHERE deleted_at IS NULL;
CREATE INDEX IF NOT EXISTS revenues_district_fy_idx ON revenues (district_id, financial_year_id) WHERE deleted_at IS NULL;
CREATE INDEX IF NOT EXISTS revenues_metric_idx      ON revenues (metric) WHERE deleted_at IS NULL;
CREATE INDEX IF NOT EXISTS revenues_published_idx   ON revenues (published_at) WHERE published_at IS NOT NULL;

CREATE INDEX IF NOT EXISTS sales_volumes_fy_idx          ON sales_volumes (financial_year_id) WHERE deleted_at IS NULL;
CREATE INDEX IF NOT EXISTS sales_volumes_district_fy_idx ON sales_volumes (district_id, financial_year_id) WHERE deleted_at IS NULL;
CREATE INDEX IF NOT EXISTS sales_volumes_metric_idx      ON sales_volumes (metric) WHERE deleted_at IS NULL;
CREATE INDEX IF NOT EXISTS sales_volumes_published_idx   ON sales_volumes (published_at) WHERE published_at IS NOT NULL;

CREATE INDEX IF NOT EXISTS operations_fy_idx          ON operations (financial_year_id) WHERE deleted_at IS NULL;
CREATE INDEX IF NOT EXISTS operations_district_fy_idx ON operations (district_id, financial_year_id) WHERE deleted_at IS NULL;
CREATE INDEX IF NOT EXISTS operations_metric_idx      ON operations (metric) WHERE deleted_at IS NULL;
CREATE INDEX IF NOT EXISTS operations_published_idx   ON operations (published_at) WHERE published_at IS NOT NULL;

CREATE INDEX IF NOT EXISTS shops_district_idx    ON shops (district_id) WHERE deleted_at IS NULL;
CREATE INDEX IF NOT EXISTS shop_years_fy_type_idx ON shop_years (financial_year_id, shop_type);
CREATE INDEX IF NOT EXISTS brand_prices_fy_idx   ON brand_prices (financial_year_id);

-- ---------------------------------------------------------------------------
-- updated_at triggers — one BEFORE UPDATE trigger per public table that has an
-- updated_at column. Driven off the catalog so it stays in step with the
-- tables above.
-- ---------------------------------------------------------------------------

DO $$
DECLARE t text;
BEGIN
    FOR t IN
        SELECT table_name
        FROM information_schema.columns
        WHERE table_schema = 'public' AND column_name = 'updated_at'
    LOOP
        EXECUTE format('DROP TRIGGER IF EXISTS trg_%1$s_updated_at ON %1$I', t);
        EXECUTE format(
            'CREATE TRIGGER trg_%1$s_updated_at BEFORE UPDATE ON %1$I '
            'FOR EACH ROW EXECUTE FUNCTION set_updated_at()', t);
    END LOOP;
END;
$$;

RESET ROLE;
