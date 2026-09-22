MODEL (
  name analytics.taoec.competing_countries_products,
  kind VIEW,
  description 'Products traded by countries appearing the top 5% pairs with highest ESI.',
  column_descriptions (
    product_id = 'Numeric product ID'
  ),
  audits (
    not_null(columns := (product_id)),
    unique_values(columns := (product_id))
  )
);

SELECT DISTINCT
    product_id
FROM
    analytics.taoec.hs92_ccp_trade_3y_latest
WHERE
    country_id IN (
        SELECT country_id
        FROM analytics.taoec.competing_countries
    )
    OR partner_country_id IN (
        SELECT country_id
        FROM analytics.taoec.competing_countries
    )
