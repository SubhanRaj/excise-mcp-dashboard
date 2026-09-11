-- roles.sql — the three PostgreSQL roles for excise_bank.
--
-- Run once by the operator as a cluster superuser, before schema.sql:
--
--   sudo -u postgres psql -d excise_bank \
--     -v owner_pw="..." -v etl_pw="..." -v ro_pw="..." \
--     -f roles.sql
--
-- Passwords come from psql -v vars, never a literal in this file. Pass the
-- raw password only, no surrounding quotes — :'owner_pw' below already adds
-- them; a value like -v owner_pw="'...'" double-quotes it and the literal
-- quote characters end up baked into the password (hit this once for real).
-- db:provision is MariaDB-only and is not used here.
--
-- | Role         | Rights                                          | Used by               |
-- |--------------|-------------------------------------------------|-----------------------|
-- | excise_owner | owns the database and every schema; DDL         | migrations (operator) |
-- | excise_etl   | INSERT/UPDATE/DELETE on public.* + kb.* + etl.* | etl/ cron jobs        |
-- | excise_ro    | SELECT on analytics.* + kb.* only; read-only    | orchestrator (AI path)|

\set ON_ERROR_STOP on

-- Owner: schema DDL only. Given LOGIN so the operator can run migrations as it;
-- no service connects as excise_owner at runtime.
CREATE ROLE excise_owner LOGIN PASSWORD :'owner_pw';
ALTER DATABASE excise_bank OWNER TO excise_owner;

-- Schemas are created here, ahead of schema.sql, so the grants below resolve
-- (this script runs first). schema.sql re-declares each with
-- CREATE SCHEMA IF NOT EXISTS and fills it. public is reassigned to excise_owner
-- so the owner can create tables in it under SET ROLE.
ALTER SCHEMA public OWNER TO excise_owner;
CREATE SCHEMA IF NOT EXISTS kb        AUTHORIZATION excise_owner;
CREATE SCHEMA IF NOT EXISTS etl       AUTHORIZATION excise_owner;
CREATE SCHEMA IF NOT EXISTS analytics AUTHORIZATION excise_owner;

-- ETL writer: data tables, kb.*, and etl bookkeeping. No CREATE — it cannot add
-- or drop tables.
CREATE ROLE excise_etl LOGIN PASSWORD :'etl_pw';
GRANT CONNECT ON DATABASE excise_bank TO excise_etl;
GRANT USAGE ON SCHEMA public, kb, etl TO excise_etl;
GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public, kb, etl TO excise_etl;
GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public, kb, etl TO excise_etl;
ALTER DEFAULT PRIVILEGES FOR ROLE excise_owner IN SCHEMA public, kb, etl
    GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO excise_etl;

-- Read-only AI role: analytics views and the knowledge base, nothing else.
CREATE ROLE excise_ro LOGIN PASSWORD :'ro_pw';
GRANT CONNECT ON DATABASE excise_bank TO excise_ro;
GRANT USAGE ON SCHEMA analytics, kb TO excise_ro;
GRANT SELECT ON ALL TABLES IN SCHEMA analytics, kb TO excise_ro;
ALTER DEFAULT PRIVILEGES FOR ROLE excise_owner IN SCHEMA analytics, kb
    GRANT SELECT ON TABLES TO excise_ro;

-- excise_ro must not see the base data or write anywhere.
REVOKE ALL ON SCHEMA public, etl FROM excise_ro;
REVOKE CREATE ON SCHEMA public, kb, analytics FROM PUBLIC;   -- no ad-hoc object creation by anyone
REVOKE ALL ON DATABASE excise_bank FROM PUBLIC;

-- Force read-only at the session level, on top of the per-transaction READ ONLY
-- the orchestrator wraps every query in.
ALTER ROLE excise_ro SET default_transaction_read_only = on;
ALTER ROLE excise_ro SET statement_timeout = '10s';
ALTER ROLE excise_ro SET idle_in_transaction_session_timeout = '15s';
ALTER ROLE excise_ro SET lock_timeout = '2s';
ALTER ROLE excise_ro SET search_path = analytics, kb;
