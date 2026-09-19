-- 1. Create Silver Schema
CREATE SCHEMA IF NOT EXISTS silver;

-- 2. Clean, Cast, and Compact into Silver
CREATE TABLE IF NOT EXISTS silver.vpc_flowlogs AS
SELECT
    -- Explicitly align types to prevent mixed BYTE_ARRAY / INT64 drift
    TRY_CAST(NULLIF(version, '-') AS INTEGER) AS version,
    TRY_CAST(NULLIF(account_id, '-') AS VARCHAR) AS account_id,
    TRY_CAST(NULLIF(interface_id, '-') AS VARCHAR) AS interface_id,
    TRY_CAST(NULLIF(srcaddr, '-') AS VARCHAR) AS srcaddr,
    TRY_CAST(NULLIF(dstaddr, '-') AS VARCHAR) AS dstaddr,

    -- Cast ports & metrics to tight numeric types
    TRY_CAST(NULLIF(sp, '-') AS INTEGER) AS sp,
    TRY_CAST(NULLIF(dp, '-') AS INTEGER) AS dp,
    TRY_CAST(NULLIF(protocol, '-') AS SMALLINT) AS protocol,
    TRY_CAST(NULLIF(packets, '-') AS BIGINT) AS pkt,
    TRY_CAST(NULLIF(bytes, '-') AS BIGINT) AS byt,

    -- Cast UNIX epoch seconds to timestamps
    epoch_ms(TRY_CAST(NULLIF("start", '-') AS BIGINT) * 1000) AS start_time,
    epoch_ms(TRY_CAST(NULLIF("end", '-') AS BIGINT) * 1000) AS end_time,

    TRY_CAST(NULLIF(action, '-') AS VARCHAR) AS action,
    TRY_CAST(NULLIF(log_status, '-') AS VARCHAR) AS log_status,

    -- Partition columns carried from Bronze
    year,
    month
FROM bronze.vpc_flowlogs;
