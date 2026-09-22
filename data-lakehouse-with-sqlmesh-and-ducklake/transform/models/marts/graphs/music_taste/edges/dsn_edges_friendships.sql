MODEL (
  name graphs.music_taste.dsn_edges_friendships,
  kind FULL,
  description 'Deezer friendship relations between users',
  column_descriptions (
    source_id = 'Source user node ID',
    target_id = 'Target user node ID'
  ),
  audits (
    not_null(columns := (source_id, target_id)),
    unique_combination_of_columns(columns := (source_id, target_id)),
    relationships(
      column := source_id,
      to := graphs.music_taste.dsn_nodes_users,
      field := node_id
    ),
    relationships(
      column := target_id,
      to := graphs.music_taste.dsn_nodes_users,
      field := node_id
    )
  )
);

WITH all_edges AS (
    SELECT
        source_id,
        target_id,
        'HR' AS country
    FROM stage.dsn.hr_edges

    UNION

    SELECT
        source_id,
        target_id,
        'HU' AS country
    FROM stage.dsn.hu_edges

    UNION

    SELECT
        source_id,
        target_id,
        'RO' AS country
    FROM stage.dsn.ro_edges
)
SELECT sn.node_id AS source_id, tn.node_id AS target_id
FROM all_edges e

JOIN graphs.music_taste.dsn_nodes_users AS sn
ON e.source_id = sn.user_id AND e.country = sn.country

JOIN graphs.music_taste.dsn_nodes_users AS tn
ON e.target_id = tn.user_id AND e.country = tn.country

ORDER BY source_id, target_id
