MODEL (
  name graphs.music_taste.msdsl_edges_track_tags,
  kind FULL,
  description 'Million Song Dataset, Spotify, and Last.fm (MSDSL) track tags',
  column_descriptions (
    source_id = 'Track node ID',
    target_id = 'Genre node ID (only for tags matching Deezer genres)'
  ),
  audits (
    not_null(columns := (source_id, target_id)),
    unique_combination_of_columns(columns := (source_id, target_id)),
    relationships(
      column := source_id,
      to := graphs.music_taste.msdsl_nodes_tracks,
      field := node_id
    ),
    relationships(
      column := target_id,
      to := graphs.music_taste.nodes_genres,
      field := node_id
    )
  )
);

WITH track_genres AS (
    SELECT track_id, unnest(tags) AS genre
    FROM stage.msdsl.music_info
)
SELECT sn.node_id AS source_id, tn.node_id AS target_id
FROM track_genres tg

JOIN graphs.music_taste.msdsl_nodes_tracks AS sn
ON tg.track_id = sn.track_id

JOIN graphs.music_taste.nodes_genres AS tn
ON tg.genre = tn.genre
