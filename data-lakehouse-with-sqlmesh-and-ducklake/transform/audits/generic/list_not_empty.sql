AUDIT (
  name list_not_empty,
  dialect duckdb,
);

SELECT *
FROM @this_model
WHERE @column IS NULL
    OR len(@column) = 0
