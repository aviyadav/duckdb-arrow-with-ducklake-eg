MODEL (
  name graphs.econ_comp.nodes_countries,
  kind FULL,
  description 'Nodes for countries in the Economic Competition Network.',
  column_descriptions (
    node_id = 'Unique numerical node ID from a shared sequence',
    country_id = 'Numeric country ID',
    country_iso3_code = 'ISO 3166-1 alpha-3 country code',
    country_name = 'Country name',
    country_name_short = 'Short country name',
    in_rankings = 'Whether the country is included in the rankings',
    former_country = 'Whether the country no longer exists'
  ),
  audits (
    not_null(columns := (
      node_id, country_id, country_iso3_code, country_name, country_name_short,
      in_rankings, former_country
    )),
    unique_values(columns := (node_id, country_id, country_iso3_code))
  )
);

SELECT
    row_number() OVER () AS node_id,
    country_id,
    country_iso3_code,
    country_name,
    country_name_short,
    in_rankings,
    former_country
FROM
    stage.taoec.countries
WHERE
    country_id IN (
        SELECT country_id
        FROM analytics.taoec.competing_countries
    )
