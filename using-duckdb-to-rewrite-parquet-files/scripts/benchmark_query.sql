SELECT
  COUNT(*) AS total_rows,
  SUM(TRY_CAST(byt AS BIGINT)) AS total_bytes,
  ROUND(
    SUM(TRY_CAST(byt AS BIGINT)) / 1024 / 1024 / 1024,
    2
  ) AS total_gb
FROM read_parquet('<pattern>', union_by_name = true)