MODEL (
  name analytics.taoec.competing_countries,
  kind VIEW,
  description 'Competing countries according to the top 5% pairs with highest ESI.',
  column_descriptions (
    country_id = 'Numeric country ID'
  ),
  audits (
    not_null(columns := (country_id)),
    unique_values(columns := (country_id))
  )
);

WITH countries AS (
    SELECT country_id_1, country_id_2
    FROM analytics.taoec.cc_metrics
    WHERE esi > 0
)
SELECT country_id_1 AS country_id
FROM countries

UNION

SELECT country_id_2 AS country_id
FROM countries
