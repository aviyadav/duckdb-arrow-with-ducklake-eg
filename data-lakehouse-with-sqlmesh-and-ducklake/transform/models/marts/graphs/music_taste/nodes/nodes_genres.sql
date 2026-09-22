MODEL (
  name graphs.music_taste.nodes_genres,
  kind FULL,
  description 'Deezer genres and MSDSL tags as genre nodes',
  column_descriptions (
    node_id = 'Unique numerical node ID from a shared sequence',
    genre = 'All unique genres from DSN Croatian (HR), Hungarian (HU) and Romanian (RO), and all MSDSL tags as genres.'
  ),
  audits (
    not_null(columns := (node_id, genre)),
    unique_values(columns := (node_id)),
    unique_values(columns := (genre))
  )
);

-- Node IDs are drawn from one shared sequence: every model starts from the highest ID
-- already in use, so uniqueness within each model keeps IDs unique across the graph.
WITH all_genres AS (
    SELECT unnest(genres) AS genre
    FROM stage.dsn.hr_genres

    UNION

    SELECT unnest(genres) AS genre
    FROM stage.dsn.hu_genres

    UNION

    SELECT unnest(genres) AS genre
    FROM stage.dsn.ro_genres

    UNION

    SELECT unnest(tags) AS genre
    FROM stage.msdsl.music_info
),
unique_genres AS (
    SELECT DISTINCT genre
    FROM all_genres
),
n AS (
    SELECT max(node_id) + 1 AS start_node_id
    FROM graphs.music_taste.msdsl_nodes_users
)
SELECT
    n.start_node_id + row_number() OVER () AS node_id,
    genre
FROM unique_genres, n
