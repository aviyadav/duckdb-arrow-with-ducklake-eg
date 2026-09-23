{{ config(materialized='view') }}

SELECT
    *,
    filename AS _source_file
FROM read_parquet(
    '/home/avinash/codebase/python-base/building_a_better_ducklake/data/raw/**/*.parquet',
    hive_partitioning = true,
    union_by_name = true,
    filename = true
)
