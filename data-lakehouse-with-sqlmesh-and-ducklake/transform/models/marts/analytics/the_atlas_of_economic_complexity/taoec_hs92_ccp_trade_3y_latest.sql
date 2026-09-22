MODEL (
  name analytics.taoec.hs92_ccp_trade_3y_latest,
  kind VIEW,
  description 'Country Trade by Partner and Product (HS92), aggregated for the most recent 3 years.',
  column_descriptions (
    country_id = 'Numeric country ID',
    country_iso3_code = 'ISO 3166-1 alpha-3 country code',
    partner_country_id = 'Numeric partner country ID',
    partner_iso3_code = 'ISO 3166-1 alpha-3 partner country code',
    product_id = 'Numeric product ID',
    since_year = 'First year in the aggregation window',
    until_year = 'Last year in the aggregation window',
    export_value = 'Total exported value, in USD',
    import_value = 'Total imported value, in USD'
  ),
  audits (
    not_null(columns := (
      country_id, country_iso3_code, partner_country_id, partner_iso3_code,
      product_id, since_year, until_year, export_value, import_value
    ))
  )
);

SELECT
    country_id,
    country_iso3_code,
    partner_country_id,
    partner_iso3_code,
    product_id,
    product_hs92_code,
    min(year) AS since_year,
    max(year) AS until_year,
    sum(export_value) AS export_value,
    sum(import_value) AS import_value
FROM stage.taoec.hs92_ccp_trade
WHERE year >= (
    SELECT max(year) - 3
    FROM stage.taoec.hs92_ccp_trade
)
GROUP BY
    country_id,
    country_iso3_code,
    partner_country_id,
    partner_iso3_code,
    product_id,
    product_hs92_code
