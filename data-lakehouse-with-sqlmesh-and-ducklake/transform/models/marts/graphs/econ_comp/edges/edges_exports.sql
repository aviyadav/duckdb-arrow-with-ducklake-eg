MODEL (
  name graphs.econ_comp.edges_exports,
  kind FULL,
  description 'Exported products by countries.',
  column_descriptions (
    source_id = 'Country node ID',
    target_id = 'Product node ID',
    amount_usd = 'Total exported value, in USD'
  ),
  audits (
    not_null(columns := (source_id, target_id, amount_usd)),
    positive_integer(column := amount_usd)
  )
);

SELECT
    sn.node_id AS source_id,
    tn.node_id AS target_id,
    sum(export_value) AS amount_usd
FROM
    analytics.taoec.hs92_ccp_trade_3y_latest AS t
JOIN
    graphs.econ_comp.nodes_countries AS sn
    ON t.country_id = sn.country_id
JOIN
    graphs.econ_comp.nodes_products AS tn
    ON t.product_id = tn.product_id
WHERE
    export_value > 0
GROUP BY
    source_id,
    target_id
