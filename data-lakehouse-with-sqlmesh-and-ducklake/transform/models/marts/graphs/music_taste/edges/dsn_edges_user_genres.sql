MODEL (
  name graphs.music_taste.dsn_edges_user_genres,
  kind FULL,
  description 'Deezer user preferred music genres',
  column_descriptions (
    source_id = 'Deezer user node ID',
    target_id = 'Genre node ID'
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
      to := graphs.music_taste.nodes_genres,
      field := node_id
    )
  )
);

WITH user_genres AS (
    SELECT
        user_id,
        unnest(genres) AS genre,
        'HR' AS country
    FROM stage.dsn.hr_genres

    UNION

    SELECT
        user_id,
        unnest(genres) AS genre,
        'HU' AS country
    FROM stage.dsn.hu_genres

    UNION

    SELECT
        user_id,
        unnest(genres) AS genre,
        'RO' AS country
    FROM stage.dsn.ro_genres
)

SELECT sn.node_id AS source_id, tn.node_id AS target_id
FROM user_genres ug

JOIN graphs.music_taste.dsn_nodes_users AS sn
ON ug.user_id = sn.user_id AND sn.country = ug.country

JOIN graphs.music_taste.nodes_genres AS tn
ON ug.genre = tn.genre
