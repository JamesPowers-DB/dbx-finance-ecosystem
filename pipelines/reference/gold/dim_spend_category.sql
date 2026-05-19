-- ============================================================================
-- GOLD — dim_spend_category (2-tier spend taxonomy)
-- ============================================================================
-- The authoritative pipeline materialization of the spend taxonomy. Mirrors
-- `data/generators/_lib.SPEND_CATEGORY_HIERARCHY` — those two stay in sync via
-- the reconcile step (99_reconcile.py), which fails the data-gen job if the
-- leaf sets diverge.
--
-- Grain: one row per (primary_code, secondary_code) leaf. secondary_code is
-- the primary key — 30 rows total across 8 parents.
--
-- Consumers:
--   - silver/gold spend pipeline references this dim to validate true_category_*
--     values and to derive `direct_indirect` consistently.
--   - ML batch inference joins this table to derive `predicted_primary_category`
--     from the leaf-level argmax.
-- ============================================================================

CREATE OR REFRESH MATERIALIZED VIEW ${schema_gold}.dim_spend_category
COMMENT "2-tier spend taxonomy — 8 parents × 30 leaves. Source of truth for predicted_primary_category derivation and for the demo's supervised label set."
AS
SELECT
  primary_code,
  primary_name,
  secondary_code,
  secondary_name,
  gl_account,
  gl_account_type,
  CAST(gl_account_type = 'COGS' AS BOOLEAN)  AS is_direct,
  segment_affinity
FROM VALUES
  -- Direct Materials & Components (12)
  ('Direct_Materials_Components', 'Direct Materials & Components', 'Aerospace_Components',  'Aerospace Components',  '5000', 'COGS', 'HAD'),
  ('Direct_Materials_Components', 'Direct Materials & Components', 'Hydraulic_Systems',     'Hydraulic Systems',     '5000', 'COGS', 'HAD'),
  ('Direct_Materials_Components', 'Direct Materials & Components', 'Composite_Materials',   'Composite Materials',   '5000', 'COGS', 'HAD'),
  ('Direct_Materials_Components', 'Direct Materials & Components', 'Industrial_Sensors',    'Industrial Sensors',    '5000', 'COGS', 'HPA'),
  ('Direct_Materials_Components', 'Direct Materials & Components', 'Control_Systems',       'Control Systems',       '5000', 'COGS', 'HPA'),
  ('Direct_Materials_Components', 'Direct Materials & Components', 'HVAC_Equipment',        'HVAC Equipment',        '5000', 'COGS', 'HSB'),
  ('Direct_Materials_Components', 'Direct Materials & Components', 'Building_Controls',     'Building Controls',     '5000', 'COGS', 'HSB'),
  ('Direct_Materials_Components', 'Direct Materials & Components', 'Security_Systems',      'Security Systems',      '5000', 'COGS', 'HSB'),
  ('Direct_Materials_Components', 'Direct Materials & Components', 'Fire_Suppression',      'Fire Suppression',      '5000', 'COGS', 'HSB'),
  ('Direct_Materials_Components', 'Direct Materials & Components', 'Solar_Components',      'Solar Components',      '5000', 'COGS', 'HET'),
  ('Direct_Materials_Components', 'Direct Materials & Components', 'Battery_Materials',     'Battery Materials',     '5000', 'COGS', 'HET'),
  ('Direct_Materials_Components', 'Direct Materials & Components', 'Power_Electronics',     'Power Electronics',     '5000', 'COGS', 'HET'),
  -- Raw Materials (2)
  ('Raw_Materials',                'Raw Materials',                'Raw_Materials_Metals',   'Raw Materials — Metals',   '5000', 'COGS', 'CROSS'),
  ('Raw_Materials',                'Raw Materials',                'Raw_Materials_Polymers', 'Raw Materials — Polymers', '5000', 'COGS', 'CROSS'),
  -- MRO & Field Services (2)
  ('MRO_Field_Services',           'MRO & Field Services',          'MRO_Services_Aero',     'MRO Services — Aero',      '5030', 'COGS', 'HAD'),
  ('MRO_Field_Services',           'MRO & Field Services',          'Calibration_Services',  'Calibration Services',     '5030', 'COGS', 'HPA'),
  -- Software & Cloud (3)
  ('Software_Cloud',               'Software & Cloud',              'Process_Software',      'Process Software',         '6040', 'SGA',  'HPA'),
  ('Software_Cloud',               'Software & Cloud',              'Monitoring_Software',   'Monitoring Software',      '6040', 'SGA',  'HET'),
  ('Software_Cloud',               'Software & Cloud',              'Cloud_Infrastructure',  'Cloud Infrastructure',     '6050', 'SGA',  'CROSS'),
  -- IT & Telecom (2)
  ('IT_Telecom',                   'IT & Telecom',                  'IT_Services',           'IT Services',              '6050', 'SGA',  'CROSS'),
  ('IT_Telecom',                   'IT & Telecom',                  'Telecommunications',    'Telecommunications',       '6110', 'SGA',  'CROSS'),
  -- Professional Services (3)
  ('Professional_Services',        'Professional Services',         'Professional_Services_Legal',      'Professional Services — Legal',      '6060', 'SGA', 'CROSS'),
  ('Professional_Services',        'Professional Services',         'Professional_Services_Audit',      'Professional Services — Audit',      '6070', 'SGA', 'CROSS'),
  ('Professional_Services',        'Professional Services',         'Professional_Services_Consulting', 'Professional Services — Consulting', '6080', 'SGA', 'CROSS'),
  -- Facilities & G&A (5)
  ('Facilities_GA',                'Facilities & G&A',              'Office_Supplies',       'Office Supplies',          '6100', 'SGA',  'CROSS'),
  ('Facilities_GA',                'Facilities & G&A',              'Facilities',            'Facilities',               '6090', 'SGA',  'CROSS'),
  ('Facilities_GA',                'Facilities & G&A',              'Travel',                'Travel',                   '6020', 'SGA',  'CROSS'),
  ('Facilities_GA',                'Facilities & G&A',              'Marketing',             'Marketing',                '6030', 'SGA',  'CROSS'),
  ('Facilities_GA',                'Facilities & G&A',              'Training',              'Training',                 '6130', 'SGA',  'CROSS'),
  -- Logistics (1)
  ('Logistics',                    'Logistics',                     'Logistics_Freight',     'Logistics & Freight',      '6120', 'SGA',  'CROSS')
AS t(primary_code, primary_name, secondary_code, secondary_name, gl_account, gl_account_type, segment_affinity);
