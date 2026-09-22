MODEL (
  name stage.dsn.hu_edges,
  kind FULL,
  description 'Hungarian users with friendship relations on Deezer',
  column_descriptions (
    source_id = 'Source user node ID',
    target_id = 'Target user node ID'
  ),
  audits (
    not_null(columns := (source_id, target_id))
  )
);

JINJA_QUERY_BEGIN;

{{ load_deezer_edges(var('RAW__DEEZER_SOCIAL_NETWORKS__HU__HU_EDGES')) }}

JINJA_QUERY_END;
