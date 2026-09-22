MODEL (
  name stage.taoec.countries,
  kind FULL,
  column_descriptions (
    country_id = 'Numeric country ID',
    country_iso3_code = 'ISO 3166-1 alpha-3 country code',
    country_name = 'Country name',
    country_name_short = 'Short country name',
    in_rankings = 'Whether the country is included in the rankings',
    former_country = 'Whether the country no longer exists'
  ),
  audits (
    not_null(columns := (
      country_id, country_iso3_code, country_name, country_name_short,
      in_rankings, former_country
    ))
  )
);

SELECT
    country_id,
    country_iso3_code,
    country_name,
    country_name_short,
    in_rankings,
    former_country
FROM read_csv(
    @RAW__THE_ATLAS_OF_ECONOMIC_COMPLEXITY__CLASSIFICATIONS__LOCATION_COUNTRY,
    delim = ',',
    quote = '"',
    escape = '"',
    header = true,
    columns = {
        country_id: USMALLINT,
        country_iso3_code: VARCHAR,
        country_name: VARCHAR,
        country_name_short: VARCHAR,
        in_rankings: BOOLEAN,
        former_country: BOOLEAN
    }
)
