MODEL (
  name graphs.music_taste.msdsl_nodes_users,
  kind FULL,
  description 'Million Song Dataset, Spotify, and Last.fm users',
  column_descriptions (
    node_id = 'Unique numerical node ID from a shared sequence',
    user_id = 'User ID for Million Song Dataset, Spotify, and Last.fm (MSDSL)',
    source = 'Data source for the node (always MSDSL)'
  ),
  audits (
    not_null(columns := (node_id, user_id)),
    unique_values(columns := (node_id)),
    expression_is_true(condition := source = 'MSDSL')
  )
);

WITH all_users AS (
    SELECT DISTINCT user_id
    FROM stage.msdsl.user_listening_history
),
n AS (
    SELECT max(node_id) + 1 AS start_node_id
    FROM graphs.music_taste.msdsl_nodes_tracks
)
SELECT DISTINCT
    n.start_node_id + row_number() OVER () AS node_id,
    user_id,
    'MSDSL' AS source
FROM all_users, n
