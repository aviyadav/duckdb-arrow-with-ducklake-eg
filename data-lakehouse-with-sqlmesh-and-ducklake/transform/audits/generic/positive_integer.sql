AUDIT (
  name positive_integer,
  dialect duckdb,
);

SELECT *
FROM @this_model
WHERE @column IS NULL
    OR @column <= 0
    OR CAST(@column AS TEXT) !~ '^\d+$'
