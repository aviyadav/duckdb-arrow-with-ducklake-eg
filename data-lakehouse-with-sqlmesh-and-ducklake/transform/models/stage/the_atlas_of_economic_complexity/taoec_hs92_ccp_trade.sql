MODEL (
  name stage.taoec.hs92_ccp_trade,
  kind FULL,
  description 'Country Trade by Partner and Product (HS92), covering only 2020-2023.',
  column_descriptions (
    country_id = 'Numeric country ID',
    country_iso3_code = 'ISO 3166-1 alpha-3 country code',
    partner_country_id = 'Numeric partner country ID',
    partner_iso3_code = 'ISO 3166-1 alpha-3 partner country code',
    product_id = 'Numeric product ID',
    year = 'Year of the trade observation',
    export_value = 'Total exported value, in USD',
    import_value = 'Total imported value, in USD'
  ),
  audits (
    not_null(columns := (
      country_id, country_iso3_code, partner_country_id, partner_iso3_code,
      product_id, year, export_value, import_value
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
    year,
    export_value,
    import_value
FROM read_csv(
    @RAW__THE_ATLAS_OF_ECONOMIC_COMPLEXITY__HS92__HS92_COUNTRY_COUNTRY_PRODUCT_YEAR_6_2020_2023,
    delim = ',',
    quote = '"',
    escape = '"',
    header = true,
    nullstr = ['XXXXXX'],
    columns = {
        country_id: USMALLINT,
        country_iso3_code: VARCHAR,
        partner_country_id: USMALLINT,
        partner_iso3_code: VARCHAR,
        product_id: USMALLINT,
        product_hs92_code: UINTEGER,
        year: USMALLINT,
        export_value: BIGINT,
        import_value: BIGINT
    }
)
