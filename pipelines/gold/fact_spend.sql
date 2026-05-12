-- ============================================================================
-- GOLD — fact_spend (PO-line grain, the ML training payload)
-- ============================================================================
-- One row per PO line. This is the *primary* table the spend-classification
-- model is trained against. `true_spend_category` is the supervised label.
-- Phase 2 hooks (NULL today, populated by ML model later):
--   managed_spend_flag, unspsc_segment_code, unspsc_family_code,
--   supplier_canonical_id, classification_confidence
-- ============================================================================

CREATE OR REFRESH MATERIALIZED VIEW ${schema_gold}.fact_spend
COMMENT "PO-line spend fact. Carries ML features (line_description, material_group, supplier metadata, extended_amount) and the true_spend_category label. Phase 2 spend-classification model writes back into unspsc_*/classification_confidence/managed_spend_flag."
AS
SELECT
  po.po_number,
  po.po_line_num,
  po.po_created_date,
  po.fiscal_year,
  po.fiscal_quarter,
  po.po_doc_type,
  po.supplier_id,
  s.supplier_name,
  s.region                                     AS supplier_region,
  s.country_code                               AS supplier_country,
  s.maverick_propensity                        AS supplier_maverick_propensity,
  s.segment_affinity                           AS supplier_segment_affinity,
  po.buyer_company_code,
  po.segment_code,
  po.material_number,
  po.material_group_code,
  po.line_description,
  po.quantity,
  po.uom,
  po.unit_price,
  po.price_unit,
  po.extended_amount,
  po.currency,
  -- Supervised label for ML
  po.true_spend_category,
  -- Phase 2 hooks — populated by the spend-classification model post-training
  CAST(NULL AS BOOLEAN)  AS managed_spend_flag,
  CAST(NULL AS STRING)   AS unspsc_segment_code,
  CAST(NULL AS STRING)   AS unspsc_family_code,
  s.canonical_supplier_id,
  CAST(NULL AS DOUBLE)   AS classification_confidence
FROM ${schema_silver}.purchase_order po
LEFT JOIN ${schema_gold}.dim_supplier s
  ON po.supplier_id = s.supplier_id;
