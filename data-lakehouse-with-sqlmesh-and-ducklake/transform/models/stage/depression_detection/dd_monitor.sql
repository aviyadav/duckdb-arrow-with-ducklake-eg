MODEL (
  name stage.dd.monitor,
  kind FULL,
  column_descriptions (
    example_id = 'Unique example identifier',
    input = 'Text of the social media post',
    target = 'Whether the post is about depression'
  )
);

SELECT
    row_number() OVER () AS example_id,
    text AS input,
    CAST(label AS DOUBLE) AS target
FROM read_csv(
    @RAW__DEPRESSION__CLEAN_ENCODED_DF,
    delim = ',',
    header = true,
    columns = {
        text: VARCHAR,
        label: USMALLINT
    }
)
