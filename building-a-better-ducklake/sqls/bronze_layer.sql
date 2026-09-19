-- 1. Create Bronze Schema
CREATE SCHEMA IF NOT EXISTS bronze;

-- 2. Ingest Raw Parquet Files (1:1 with Source)
CREATE TABLE IF NOT EXISTS bronze.vpc_flowlogs AS
SELECT *
FROM read_parquet(
    'data/raw/**/*.parquet',
    hive_partitioning = true,
    union_by_name = true
);
