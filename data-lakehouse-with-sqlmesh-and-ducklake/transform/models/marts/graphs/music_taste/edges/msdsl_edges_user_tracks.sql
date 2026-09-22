MODEL (
  name graphs.music_taste.msdsl_edges_user_tracks,
  kind FULL,
  description 'Million Song Dataset, Spotify, and Last.fm (MSDSL) user tracks',
  column_descriptions (
    source_id = 'MSDSL user node ID',
    target_id = 'Track node ID',
    play_count = 'Number of times the user played the track'
  ),
  audits (
    not_null(columns := (source_id, target_id)),
    unique_combination_of_columns(columns := (source_id, target_id)),
    relationships(
      column := source_id,
      to := graphs.music_taste.msdsl_nodes_users,
      field := node_id
    ),
    relationships(
      column := target_id,
      to := graphs.music_taste.msdsl_nodes_tracks,
      field := node_id
    )
  )
);

SELECT
    sn.node_id AS source_id,
    tn.node_id AS target_id,
    play_count
FROM stage.msdsl.user_listening_history uh

JOIN graphs.music_taste.msdsl_nodes_users AS sn
ON uh.user_id = sn.user_id

JOIN graphs.music_taste.msdsl_nodes_tracks AS tn
ON uh.track_id = tn.track_id
