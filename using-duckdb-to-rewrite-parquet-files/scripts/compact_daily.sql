COPY (
  SELECT *
  FROM read_parquet(
    '*_vpcflowlogs_*_YYYYMMDDT*.parquet',
    union_by_name = true
  )
)
TO 'daily-YYYY-MM-DD.parquet'
(FORMAT PARQUET, COMPRESSION ZSTD);