-- ============================================================================
-- GOLD — dim_segment
-- ============================================================================

CREATE OR REFRESH MATERIALIZED VIEW ${schema_gold}.dim_segment
COMMENT "Helios reporting segments + corporate. Static."
AS
SELECT segment_code, segment_name, company_code, sort_order FROM VALUES
  ('HAD',  'Helios Aerospace & Defense',  '1100', 1),
  ('HPA',  'Helios Process Automation',   '1200', 2),
  ('HSB',  'Helios Smart Buildings',      '1300', 3),
  ('HET',  'Helios Energy Transition',    '1400', 4),
  ('CORP', 'Helios Corporate',            '1900', 5),
  ('CONSOL','Helios Industrial Group (Consolidated)', NULL, 0)
  AS t(segment_code, segment_name, company_code, sort_order);
