MODEL (
  name graphs.econ_comp.edges_imports,
  kind FULL,
  description 'Imported products by countries.',
  column_descriptions (
    source_id = 'Product node ID',
    target_id = 'Country node ID',
    amount_usd = 'Total imported value, in USD'
  ),
  audits (
    not_null(columns := (source_id, target_id, amount_usd)),
    positive_integer(column := amount_usd)
  )
);

SELECT
    sn.node_id AS source_id,
    tn.node_id AS target_id,
    sum(import_value) AS amount_usd
FROM
    analytics.taoec.hs92_ccp_trade_3y_latest AS t
JOIN
    graphs.econ_comp.nodes_products AS sn
    ON t.product_id = sn.product_id
JOIN
    graphs.econ_comp.nodes_countries AS tn
    ON t.country_id = tn.country_id
WHERE
    import_value > 0
GROUP BY
    source_id,
    target_id
