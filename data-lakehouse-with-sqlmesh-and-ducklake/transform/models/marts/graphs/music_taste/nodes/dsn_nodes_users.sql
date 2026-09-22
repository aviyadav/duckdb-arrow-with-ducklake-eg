MODEL (
  name graphs.music_taste.dsn_nodes_users,
  kind FULL,
  description 'Deezer user nodes',
  column_descriptions (
    node_id = 'Unique numerical node ID from a shared sequence',
    user_id = 'Deezer user ID',
    source = 'Data source for the node (always Deezer)',
    country = 'Deezer user country'
  ),
  audits (
    not_null(columns := (node_id, user_id)),
    unique_values(columns := (node_id)),
    expression_is_true(condition := source = 'Deezer'),
    expression_is_true(condition := country IN ('HR', 'HU', 'RO'))
  )
);

WITH all_users AS (
    SELECT
        g.user_id AS user_id,
        'HR' AS country
    FROM stage.dsn.hr_genres AS g

    UNION

    SELECT
        g.user_id AS user_id,
        'HU' AS country
    FROM stage.dsn.hu_genres AS g

    UNION

    SELECT
        g.user_id AS user_id,
        'RO' AS country
    FROM stage.dsn.ro_genres AS g
)
SELECT
    row_number() OVER () AS node_id,
    user_id,
    country,
    'Deezer' AS source
FROM all_users
