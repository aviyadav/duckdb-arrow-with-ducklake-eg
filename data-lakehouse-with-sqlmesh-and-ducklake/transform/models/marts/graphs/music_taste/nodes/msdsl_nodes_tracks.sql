MODEL (
  name graphs.music_taste.msdsl_nodes_tracks,
  kind FULL,
  description 'Million Song Dataset, Spotify, and Last.fm music tracks',
  column_descriptions (
    node_id = 'Unique numerical node ID from a shared sequence',
    track_id = 'String track identifier starting with TR',
    name = 'Track title',
    artist = 'Track artist',
    year = 'Track release year'
  ),
  audits (
    not_null(columns := (node_id, track_id, name, artist, year)),
    unique_values(columns := (node_id, track_id))
  )
);

WITH n AS (
    SELECT max(node_id) AS start_node_id
    FROM graphs.music_taste.dsn_nodes_users
)
SELECT
    n.start_node_id + row_number() OVER () AS node_id,
    track_id,
    name,
    artist,
    year
FROM stage.msdsl.music_info, n
