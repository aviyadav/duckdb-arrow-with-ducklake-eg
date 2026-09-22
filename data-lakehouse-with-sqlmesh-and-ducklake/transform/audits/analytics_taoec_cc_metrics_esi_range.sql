AUDIT (
  name esi_range,
  dialect duckdb,
);

SELECT *
FROM @this_model
WHERE esi < 0 OR esi > 1
