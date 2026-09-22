AUDIT (
  name relationships,
  dialect duckdb,
);

SELECT *
FROM @this_model
WHERE @column IS NOT NULL
    AND @column NOT IN (
        SELECT @field
        FROM @to
    )
