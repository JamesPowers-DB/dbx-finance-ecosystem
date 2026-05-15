-- ============================================================================
-- GOLD — fact_gl_entries (GL line grain × COA enrichment)
-- ============================================================================

CREATE OR REFRESH MATERIALIZED VIEW ${schema_gold}.fact_gl_entries
COMMENT "GL line entries enriched with COA segments + account type. The foundation for fact_fpa_actuals / trial-balance roll-ups."
AS
SELECT
  l.je_header_id,
  l.je_line_num,
  h.period_name,
  h.posted_date,
  h.fiscal_year,
  h.fiscal_quarter,
  h.je_source,
  h.je_category,
  l.code_combination_id,
  c.entity_code,
  c.cost_center_code,
  c.natural_account_code,
  c.natural_account_type                                            AS account_type,
  c.product_code,
  c.intercompany_code,
  c.segment_code,
  l.entered_dr,
  l.entered_cr,
  l.accounted_dr,
  l.accounted_cr,
  l.net_amount,
  h.currency_code,
  l.description
FROM ${schema_silver}.gl_journal_line l
JOIN ${schema_silver}.gl_journal_header h USING (je_header_id)
LEFT JOIN ${schema_silver}.coa_account c USING (code_combination_id);
