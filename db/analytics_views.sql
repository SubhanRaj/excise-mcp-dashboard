-- analytics_views.sql — the analytics.* views the read-only AI role sees.
--
-- Apply after schema.sql, as a superuser:
--   sudo -u postgres psql -d excise_bank -f analytics_views.sql
--
-- One view per fact and reference table, plus analytics.districts (a dimension
-- that carries its own published_at / deleted_at). Every view filters
-- deleted_at IS NULL AND published_at IS NOT NULL so the model only ever reads
-- published, live rows, and exposes human labels (district name + slug, FY
-- label + start_year, licence-category code) next to the ids needed for joins.
--
-- The views run with the owner's privileges, so excise_ro reads them without
-- any grant on the public base tables. No view reads etl.* or the base tables
-- directly.

\set ON_ERROR_STOP on

SET ROLE excise_owner;

CREATE OR REPLACE VIEW analytics.districts AS
SELECT d.id, d.division_id, d.name, d.slug, d.lgd_code,
       d.latitude, d.longitude, d.published_at, d.created_at, d.updated_at,
       dv.name AS division, dv.slug AS division_slug,
       z.id   AS zone_id, z.name AS zone, z.slug AS zone_slug
FROM districts d
JOIN divisions dv ON dv.id = d.division_id
JOIN zones z      ON z.id = dv.zone_id
WHERE d.deleted_at IS NULL AND d.published_at IS NOT NULL;

CREATE OR REPLACE VIEW analytics.revenues AS
SELECT r.id, r.district_id, r.financial_year_id, r.license_category_id,
       r.metric, r.amount_inr, r.source_ref,
       r.published_at, r.created_at, r.updated_at,
       d.name AS district, d.slug AS district_slug,
       fy.label AS financial_year, fy.start_year,
       lc.code AS license_category
FROM revenues r
JOIN districts d        ON d.id = r.district_id
                        AND d.deleted_at IS NULL AND d.published_at IS NOT NULL
JOIN financial_years fy ON fy.id = r.financial_year_id
LEFT JOIN license_categories lc ON lc.id = r.license_category_id
WHERE r.deleted_at IS NULL AND r.published_at IS NOT NULL;

CREATE OR REPLACE VIEW analytics.sales_volumes AS
SELECT sv.id, sv.district_id, sv.financial_year_id, sv.license_category_id,
       sv.metric, sv.quantity, sv.unit, sv.source_ref,
       sv.published_at, sv.created_at, sv.updated_at,
       d.name AS district, d.slug AS district_slug,
       fy.label AS financial_year, fy.start_year,
       lc.code AS license_category
FROM sales_volumes sv
JOIN districts d        ON d.id = sv.district_id
                        AND d.deleted_at IS NULL AND d.published_at IS NOT NULL
JOIN financial_years fy ON fy.id = sv.financial_year_id
LEFT JOIN license_categories lc ON lc.id = sv.license_category_id
WHERE sv.deleted_at IS NULL AND sv.published_at IS NOT NULL;

CREATE OR REPLACE VIEW analytics.operations AS
SELECT o.id, o.district_id, o.financial_year_id,
       o.metric, o.value, o.source_ref,
       o.published_at, o.created_at, o.updated_at,
       d.name AS district, d.slug AS district_slug,
       fy.label AS financial_year, fy.start_year
FROM operations o
JOIN districts d        ON d.id = o.district_id
                        AND d.deleted_at IS NULL AND d.published_at IS NOT NULL
JOIN financial_years fy ON fy.id = o.financial_year_id
WHERE o.deleted_at IS NULL AND o.published_at IS NOT NULL;

CREATE OR REPLACE VIEW analytics.shops AS
SELECT s.id, s.district_id, s.shop_number, s.seq, s.display_name,
       s.license_category_id, s.circle_code, s.sector_code,
       s.latitude, s.longitude,
       s.published_at, s.created_at, s.updated_at,
       d.name AS district, d.slug AS district_slug,
       lc.code AS license_category
FROM shops s
JOIN districts d ON d.id = s.district_id
                 AND d.deleted_at IS NULL AND d.published_at IS NOT NULL
LEFT JOIN license_categories lc ON lc.id = s.license_category_id
WHERE s.deleted_at IS NULL AND s.published_at IS NOT NULL;

-- shop_years has no published_at / deleted_at of its own — the visibility gate
-- comes from the parent shops row.
CREATE OR REPLACE VIEW analytics.shop_years AS
SELECT sy.id, sy.shop_id, sy.financial_year_id, sy.shop_type,
       sy.mgq_bl, sy.license_fee_inr, sy.settlement_mode, sy.is_operational,
       sy.source_ref, sy.created_at, sy.updated_at,
       s.shop_number, s.display_name, s.district_id,
       d.name AS district, d.slug AS district_slug,
       fy.label AS financial_year, fy.start_year
FROM shop_years sy
JOIN shops s            ON s.id = sy.shop_id
                        AND s.deleted_at IS NULL AND s.published_at IS NOT NULL
JOIN districts d        ON d.id = s.district_id
                        AND d.deleted_at IS NULL AND d.published_at IS NOT NULL
JOIN financial_years fy ON fy.id = sy.financial_year_id;

CREATE OR REPLACE VIEW analytics.brands AS
SELECT b.id, b.name, b.license_category_id, b.segment, b.manufacturer,
       b.published_at, b.created_at, b.updated_at,
       lc.code AS license_category
FROM brands b
LEFT JOIN license_categories lc ON lc.id = b.license_category_id
WHERE b.deleted_at IS NULL AND b.published_at IS NOT NULL;

-- brand_prices has no deleted_at; the brand row carries the visibility gate.
CREATE OR REPLACE VIEW analytics.brand_prices AS
SELECT bp.id, bp.brand_id, bp.financial_year_id, bp.pack_ml,
       bp.mrp_inr, bp.ex_distillery_inr,
       bp.published_at, bp.created_at, bp.updated_at,
       b.name AS brand,
       fy.label AS financial_year, fy.start_year
FROM brand_prices bp
JOIN brands b           ON b.id = bp.brand_id
                        AND b.deleted_at IS NULL AND b.published_at IS NOT NULL
JOIN financial_years fy ON fy.id = bp.financial_year_id
WHERE bp.published_at IS NOT NULL;

-- duty_rates has no deleted_at.
CREATE OR REPLACE VIEW analytics.duty_rates AS
SELECT dr.id, dr.financial_year_id, dr.license_category_id,
       dr.basis, dr.rate, dr.unit, dr.notes,
       dr.published_at, dr.created_at, dr.updated_at,
       fy.label AS financial_year, fy.start_year,
       lc.code AS license_category
FROM duty_rates dr
JOIN financial_years fy    ON fy.id = dr.financial_year_id
JOIN license_categories lc ON lc.id = dr.license_category_id
WHERE dr.published_at IS NOT NULL;

CREATE OR REPLACE VIEW analytics.policy_entries AS
SELECT pe.id, pe.financial_year_id, pe.effective_from, pe.effective_to,
       pe.title, pe.category, pe.summary, pe.source_ref,
       pe.published_at, pe.created_at, pe.updated_at,
       fy.label AS financial_year, fy.start_year
FROM policy_entries pe
LEFT JOIN financial_years fy ON fy.id = pe.financial_year_id
WHERE pe.deleted_at IS NULL AND pe.published_at IS NOT NULL;

RESET ROLE;

-- Belt-and-suspenders: make the read-only role's access explicit even if the
-- script above ran as a role other than excise_owner (roles.sql's
-- ALTER DEFAULT PRIVILEGES already covers the excise_owner case).
GRANT USAGE ON SCHEMA analytics TO excise_ro;
GRANT SELECT ON ALL TABLES IN SCHEMA analytics TO excise_ro;
