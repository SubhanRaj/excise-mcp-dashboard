-- seed_reference.sql — the fixed reference dimensions: zones, divisions, all 75
-- UP districts with their division/zone parentage, the financial-year range, and
-- the licence categories.
--
-- Apply after schema.sql (order per db/README.md), as a superuser:
--   sudo -u postgres psql -d excise_bank -f seed_reference.sql
--
-- Source: ~/Sites/UP-excise-mailer/database/seeders/data/{zones,divisions,districts}.json
-- (the same identity + lat/long the sibling upexcise-stats-dashboard imports).
-- Every INSERT is ON CONFLICT DO NOTHING on the natural key, so a re-run is a
-- no-op. Only districts carries a published_at column; it is set on seed. zones,
-- divisions, financial_years, and license_categories have no published_at.

\set ON_ERROR_STOP on

SET ROLE excise_owner;

-- zones (5). No published_at column on this table.
INSERT INTO zones (name, slug) VALUES
  ('Meerut', 'meerut'),
  ('Agra', 'agra'),
  ('Lucknow', 'lucknow'),
  ('Gorakhpur', 'gorakhpur'),
  ('Varanasi', 'varanasi')
ON CONFLICT (name) DO NOTHING;

-- divisions (18). zone_id resolved by slug. No published_at column.
INSERT INTO divisions (zone_id, name, slug) VALUES
  ((SELECT id FROM zones WHERE slug = 'agra'), 'Agra', 'agra'),
  ((SELECT id FROM zones WHERE slug = 'agra'), 'Aligarh', 'aligarh'),
  ((SELECT id FROM zones WHERE slug = 'lucknow'), 'Ayodhya', 'ayodhya'),
  ((SELECT id FROM zones WHERE slug = 'gorakhpur'), 'Azamgarh', 'azamgarh'),
  ((SELECT id FROM zones WHERE slug = 'meerut'), 'Bareilly', 'bareilly'),
  ((SELECT id FROM zones WHERE slug = 'gorakhpur'), 'Basti', 'basti'),
  ((SELECT id FROM zones WHERE slug = 'agra'), 'Chitrakoot', 'chitrakoot'),
  ((SELECT id FROM zones WHERE slug = 'lucknow'), 'Devipatan', 'devipatan'),
  ((SELECT id FROM zones WHERE slug = 'gorakhpur'), 'Gorakhpur', 'gorakhpur'),
  ((SELECT id FROM zones WHERE slug = 'agra'), 'Jhansi', 'jhansi'),
  ((SELECT id FROM zones WHERE slug = 'agra'), 'Kanpur', 'kanpur'),
  ((SELECT id FROM zones WHERE slug = 'lucknow'), 'Lucknow', 'lucknow'),
  ((SELECT id FROM zones WHERE slug = 'meerut'), 'Meerut', 'meerut'),
  ((SELECT id FROM zones WHERE slug = 'meerut'), 'Moradabad', 'moradabad'),
  ((SELECT id FROM zones WHERE slug = 'varanasi'), 'Prayagraj', 'prayagraj'),
  ((SELECT id FROM zones WHERE slug = 'meerut'), 'Saharanpur', 'saharanpur'),
  ((SELECT id FROM zones WHERE slug = 'varanasi'), 'Varanasi', 'varanasi'),
  ((SELECT id FROM zones WHERE slug = 'varanasi'), 'Vindhyachal', 'vindhyachal')
ON CONFLICT (slug) DO NOTHING;

-- districts (75). division_id resolved by slug. published_at set on seed.
-- lgd_code is absent from the source contact list; left NULL for the ETL to fill.
INSERT INTO districts (division_id, name, slug, latitude, longitude, published_at) VALUES
  ((SELECT id FROM divisions WHERE slug = 'agra'), 'Agra', 'agra', 27.042942, 78.06981, now()),
  ((SELECT id FROM divisions WHERE slug = 'aligarh'), 'Aligarh', 'aligarh', 27.93025, 78.033208, now()),
  ((SELECT id FROM divisions WHERE slug = 'prayagraj'), 'Prayagraj', 'prayagraj', 25.324129, 81.947424, now()),
  ((SELECT id FROM divisions WHERE slug = 'ayodhya'), 'Ambedkar Nagar', 'ambedkar-nagar', 26.37926, 82.646744, now()),
  ((SELECT id FROM divisions WHERE slug = 'ayodhya'), 'Amethi', 'amethi', 26.339341, 81.667443, now()),
  ((SELECT id FROM divisions WHERE slug = 'moradabad'), 'Amroha', 'amroha', 28.859358, 78.403703, now()),
  ((SELECT id FROM divisions WHERE slug = 'kanpur'), 'Auraiya', 'auraiya', 26.688222, 79.466309, now()),
  ((SELECT id FROM divisions WHERE slug = 'ayodhya'), 'Ayodhya', 'ayodhya', 26.630671, 81.968352, now()),
  ((SELECT id FROM divisions WHERE slug = 'azamgarh'), 'Azamgarh', 'azamgarh', 26.027369, 83.052547, now()),
  ((SELECT id FROM divisions WHERE slug = 'meerut'), 'Baghpat', 'baghpat', 29.028229, 77.324642, now()),
  ((SELECT id FROM divisions WHERE slug = 'devipatan'), 'Bahraich', 'bahraich', 27.629416, 81.572178, now()),
  ((SELECT id FROM divisions WHERE slug = 'azamgarh'), 'Ballia', 'ballia', 25.849017, 84.057345, now()),
  ((SELECT id FROM divisions WHERE slug = 'devipatan'), 'Balrampur', 'balrampur', 27.401937, 82.427403, now()),
  ((SELECT id FROM divisions WHERE slug = 'chitrakoot'), 'Banda', 'banda', 25.314001, 80.523713, now()),
  ((SELECT id FROM divisions WHERE slug = 'ayodhya'), 'Barabanki', 'barabanki', 26.938295, 81.330985, now()),
  ((SELECT id FROM divisions WHERE slug = 'bareilly'), 'Bareilly', 'bareilly', 28.470088, 79.445006, now()),
  ((SELECT id FROM divisions WHERE slug = 'basti'), 'Basti', 'basti', 26.866412, 82.697195, now()),
  ((SELECT id FROM divisions WHERE slug = 'vindhyachal'), 'Bhadohi', 'bhadohi', 25.374194, 82.447441, now()),
  ((SELECT id FROM divisions WHERE slug = 'moradabad'), 'Bijnor', 'bijnor', 29.310857, 78.442236, now()),
  ((SELECT id FROM divisions WHERE slug = 'bareilly'), 'Budaun', 'budaun', 28.073069, 79.062632, now()),
  ((SELECT id FROM divisions WHERE slug = 'meerut'), 'Bulandshahr', 'bulandshahr', 28.330306, 78.000736, now()),
  ((SELECT id FROM divisions WHERE slug = 'varanasi'), 'Chandauli', 'chandauli', 25.085142, 83.263952, now()),
  ((SELECT id FROM divisions WHERE slug = 'chitrakoot'), 'Chitrakoot', 'chitrakoot', 25.14992, 81.05042, now()),
  ((SELECT id FROM divisions WHERE slug = 'gorakhpur'), 'Deoria', 'deoria', 26.444951, 83.804424, now()),
  ((SELECT id FROM divisions WHERE slug = 'aligarh'), 'Etah', 'etah', 27.505787, 78.766945, now()),
  ((SELECT id FROM divisions WHERE slug = 'kanpur'), 'Etawah', 'etawah', 26.755739, 79.088958, now()),
  ((SELECT id FROM divisions WHERE slug = 'kanpur'), 'Farrukhabad', 'farrukhabad', 27.413546, 79.456148, now()),
  ((SELECT id FROM divisions WHERE slug = 'prayagraj'), 'Fatehpur', 'fatehpur', 25.850449, 80.823029, now()),
  ((SELECT id FROM divisions WHERE slug = 'agra'), 'Firozabad', 'firozabad', 27.18699, 78.533979, now()),
  ((SELECT id FROM divisions WHERE slug = 'meerut'), 'Gautam Buddha Nagar', 'gautam-buddha-nagar', 28.350125, 77.57451, now()),
  ((SELECT id FROM divisions WHERE slug = 'meerut'), 'Ghaziabad', 'ghaziabad', 28.779815, 77.472838, now()),
  ((SELECT id FROM divisions WHERE slug = 'varanasi'), 'Ghazipur', 'ghazipur', 25.637543, 83.534171, now()),
  ((SELECT id FROM divisions WHERE slug = 'devipatan'), 'Gonda', 'gonda', 27.128371, 82.114515, now()),
  ((SELECT id FROM divisions WHERE slug = 'gorakhpur'), 'Gorakhpur', 'gorakhpur', 26.729708, 83.338722, now()),
  ((SELECT id FROM divisions WHERE slug = 'chitrakoot'), 'Hamirpur', 'hamirpur', 25.73494, 79.831699, now()),
  ((SELECT id FROM divisions WHERE slug = 'meerut'), 'Hapur', 'hapur', 28.724199, 77.883701, now()),
  ((SELECT id FROM divisions WHERE slug = 'lucknow'), 'Hardoi', 'hardoi', 27.337474, 80.212297, now()),
  ((SELECT id FROM divisions WHERE slug = 'aligarh'), 'Hathras', 'hathras', 27.566613, 78.157216, now()),
  ((SELECT id FROM divisions WHERE slug = 'jhansi'), 'Jalaun', 'jalaun', 26.077868, 79.331427, now()),
  ((SELECT id FROM divisions WHERE slug = 'varanasi'), 'Jaunpur', 'jaunpur', 25.767321, 82.589338, now()),
  ((SELECT id FROM divisions WHERE slug = 'jhansi'), 'Jhansi', 'jhansi', 25.442172, 78.895565, now()),
  ((SELECT id FROM divisions WHERE slug = 'kanpur'), 'Kannauj', 'kannauj', 27.034756, 79.642295, now()),
  ((SELECT id FROM divisions WHERE slug = 'kanpur'), 'Kanpur Dehat', 'kanpur-dehat', 26.465675, 79.942769, now()),
  ((SELECT id FROM divisions WHERE slug = 'kanpur'), 'Kanpur Nagar', 'kanpur-nagar', 26.440773, 80.159708, now()),
  ((SELECT id FROM divisions WHERE slug = 'aligarh'), 'Kasganj', 'kasganj', 27.736445, 78.843313, now()),
  ((SELECT id FROM divisions WHERE slug = 'prayagraj'), 'Kaushambi', 'kaushambi', 25.542484, 81.400616, now()),
  ((SELECT id FROM divisions WHERE slug = 'lucknow'), 'Lakhimpur Kheri', 'lakhimpur-kheri', 28.061231, 80.631967, now()),
  ((SELECT id FROM divisions WHERE slug = 'gorakhpur'), 'Kushinagar', 'kushinagar', 26.882739, 83.89652, now()),
  ((SELECT id FROM divisions WHERE slug = 'jhansi'), 'Lalitpur', 'lalitpur', 24.587145, 78.622755, now()),
  ((SELECT id FROM divisions WHERE slug = 'lucknow'), 'Lucknow', 'lucknow', 26.831408, 80.896545, now()),
  ((SELECT id FROM divisions WHERE slug = 'gorakhpur'), 'Maharajganj', 'maharajganj', 27.139296, 83.477822, now()),
  ((SELECT id FROM divisions WHERE slug = 'chitrakoot'), 'Mahoba', 'mahoba', 25.356263, 79.730229, now()),
  ((SELECT id FROM divisions WHERE slug = 'agra'), 'Mainpuri', 'mainpuri', 27.205406, 79.054242, now()),
  ((SELECT id FROM divisions WHERE slug = 'agra'), 'Mathura', 'mathura', 27.567371, 77.666304, now()),
  ((SELECT id FROM divisions WHERE slug = 'azamgarh'), 'Mau', 'mau', 26.004251, 83.552809, now()),
  ((SELECT id FROM divisions WHERE slug = 'meerut'), 'Meerut', 'meerut', 29.010478, 77.773329, now()),
  ((SELECT id FROM divisions WHERE slug = 'vindhyachal'), 'Mirzapur', 'mirzapur', 24.96279, 82.567589, now()),
  ((SELECT id FROM divisions WHERE slug = 'moradabad'), 'Moradabad', 'moradabad', 28.875259, 78.818358, now()),
  ((SELECT id FROM divisions WHERE slug = 'saharanpur'), 'Muzaffarnagar', 'muzaffarnagar', 29.43475, 77.703732, now()),
  ((SELECT id FROM divisions WHERE slug = 'bareilly'), 'Pilibhit', 'pilibhit', 28.455509, 79.936534, now()),
  ((SELECT id FROM divisions WHERE slug = 'prayagraj'), 'Pratapgarh', 'pratapgarh', 25.88682, 81.87207, now()),
  ((SELECT id FROM divisions WHERE slug = 'lucknow'), 'Raebareli', 'raebareli', 26.233653, 81.187058, now()),
  ((SELECT id FROM divisions WHERE slug = 'moradabad'), 'Rampur', 'rampur', 28.81747, 79.099196, now()),
  ((SELECT id FROM divisions WHERE slug = 'saharanpur'), 'Saharanpur', 'saharanpur', 29.900431, 77.544539, now()),
  ((SELECT id FROM divisions WHERE slug = 'moradabad'), 'Sambhal', 'sambhal', 28.476837, 78.622774, now()),
  ((SELECT id FROM divisions WHERE slug = 'basti'), 'Sant Kabir Nagar', 'sant-kabir-nagar', 26.806032, 83.03335, now()),
  ((SELECT id FROM divisions WHERE slug = 'bareilly'), 'Shahjahanpur', 'shahjahanpur', 27.968192, 79.830739, now()),
  ((SELECT id FROM divisions WHERE slug = 'saharanpur'), 'Shamli', 'shamli', 29.513816, 77.284797, now()),
  ((SELECT id FROM divisions WHERE slug = 'devipatan'), 'Shravasti', 'shravasti', 27.670874, 81.875064, now()),
  ((SELECT id FROM divisions WHERE slug = 'basti'), 'Siddharthnagar', 'siddharthnagar', 27.227502, 82.798524, now()),
  ((SELECT id FROM divisions WHERE slug = 'lucknow'), 'Sitapur', 'sitapur', 27.504209, 80.839035, now()),
  ((SELECT id FROM divisions WHERE slug = 'vindhyachal'), 'Sonbhadra', 'sonbhadra', 24.489591, 83.01253, now()),
  ((SELECT id FROM divisions WHERE slug = 'ayodhya'), 'Sultanpur', 'sultanpur', 26.264583, 82.228238, now()),
  ((SELECT id FROM divisions WHERE slug = 'lucknow'), 'Unnao', 'unnao', 26.622593, 80.636328, now()),
  ((SELECT id FROM divisions WHERE slug = 'varanasi'), 'Varanasi', 'varanasi', 25.374595, 82.88727, now())
ON CONFLICT (slug) DO NOTHING;

-- financial_years: FY2014-15 through FY2025-26. No published_at column.
INSERT INTO financial_years (label, start_year) VALUES
  ('FY2014-15', 2014),
  ('FY2015-16', 2015),
  ('FY2016-17', 2016),
  ('FY2017-18', 2017),
  ('FY2018-19', 2018),
  ('FY2019-20', 2019),
  ('FY2020-21', 2020),
  ('FY2021-22', 2021),
  ('FY2022-23', 2022),
  ('FY2023-24', 2023),
  ('FY2024-25', 2024),
  ('FY2025-26', 2025)
ON CONFLICT (start_year) DO NOTHING;

-- license_categories. No published_at column.
INSERT INTO license_categories (code, name, kind) VALUES
  ('CL', 'Country Liquor', 'country_liquor'),
  ('FL', 'Foreign Liquor', 'foreign_liquor'),
  ('BEER', 'Beer', 'beer'),
  ('BWFL', 'Bottled Wholesale Foreign Liquor', 'foreign_liquor'),
  ('MODEL', 'Model Shop', 'model_shop')
ON CONFLICT (code) DO NOTHING;

-- Reconciliation: the counts the ROADMAP Milestone 1 "Done when" calls for.
DO $$
DECLARE
    n_zones      int;
    n_divisions  int;
    n_districts  int;
    n_unmapped   int;
    n_fy         int;
BEGIN
    SELECT count(*) INTO n_zones     FROM zones;
    SELECT count(*) INTO n_divisions FROM divisions;
    SELECT count(*) INTO n_districts FROM districts;
    SELECT count(*) INTO n_unmapped
    FROM districts d
    LEFT JOIN divisions dv ON dv.id = d.division_id
    LEFT JOIN zones z      ON z.id = dv.zone_id
    WHERE dv.id IS NULL OR z.id IS NULL;
    SELECT count(*) INTO n_fy FROM financial_years;

    ASSERT n_zones = 5,        format('expected 5 zones, got %s', n_zones);
    ASSERT n_divisions = 18,   format('expected 18 divisions, got %s', n_divisions);
    ASSERT n_districts = 75,   format('expected 75 districts, got %s', n_districts);
    ASSERT n_unmapped = 0,     format('%s districts have no division/zone', n_unmapped);
    ASSERT n_fy >= 12,         format('expected at least 12 financial years, got %s', n_fy);

    RAISE NOTICE 'seed_reference: % zones, % divisions, % districts, % financial years',
        n_zones, n_divisions, n_districts, n_fy;
END;
$$;

RESET ROLE;
