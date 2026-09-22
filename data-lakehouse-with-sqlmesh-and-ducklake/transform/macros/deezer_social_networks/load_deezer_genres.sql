{% macro load_deezer_genres(s3_path) %}

-- Each file is a single JSON object mapping user IDs to genre lists. `json_each`
-- expands it into rows; DuckDB's `UNPIVOT` would be the shorter equivalent, but
-- SQLMesh's SQLGlot-based lineage cannot traverse its pivot scope.
WITH user_genres AS (
    SELECT
        CAST(j.key AS INTEGER) AS user_id,
        CAST(j.value AS VARCHAR[]) AS genres
    FROM read_json(
            '{{ s3_path }}',
            records=false,
            columns={'user_genres': 'JSON'}
         ) AS t,
         json_each(t.user_genres) AS j(key, value)
)
SELECT user_id, genres
FROM user_genres

{% endmacro %}
