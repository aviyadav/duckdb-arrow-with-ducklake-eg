AUDIT (
  name expression_is_true,
  dialect duckdb,
);

SELECT *
FROM @this_model
WHERE NOT (@condition)
