-- ============================================================================
-- GOLD — dim_segment
-- ============================================================================

CREATE OR REFRESH MATERIALIZED VIEW ${schema_gold}.dim_segment
COMMENT "reporting segments + corporate. Static."
AS
SELECT segment_code, segment_name, company_code, sort_order FROM VALUES
  ('AD',  'Aerospace & Defense',  '1100', 1),
  ('PA',  'Process Automation',   '1200', 2),
  ('SB',  'Smart Buildings',      '1300', 3),
  ('ET',  'Energy Transition',    '1400', 4),
  ('CORP', 'Corporate',            '1900', 5),
  ('CONSOL','Consolidated', NULL, 0)
  AS t(segment_code, segment_name, company_code, sort_order);
