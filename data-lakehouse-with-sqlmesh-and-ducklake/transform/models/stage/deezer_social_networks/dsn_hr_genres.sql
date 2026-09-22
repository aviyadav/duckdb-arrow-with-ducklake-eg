MODEL (
  name stage.dsn.hr_genres,
  kind FULL,
  description 'Croatia genres per user',
  column_descriptions (
    user_id = 'User ID, also the graph node ID suffix',
    genres = 'List of genres, formatted using title case'
  ),
  audits (
    not_null(columns := (user_id)),
    list_not_empty(column := genres)
  )
);

JINJA_QUERY_BEGIN;

{{ load_deezer_genres(var('RAW__DEEZER_SOCIAL_NETWORKS__HR__HR_GENRES')) }}

JINJA_QUERY_END;
