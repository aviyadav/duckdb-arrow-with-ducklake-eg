{{ config(
    materialized='incremental',
    incremental_strategy='append',
) }}

WITH bronze_source AS (
    SELECT
        TRY_CAST(NULLIF(sp, '-') AS INTEGER) AS sp,
        TRY_CAST(NULLIF(dp, '-') AS INTEGER) AS dp,
        TRY_CAST(NULLIF(protocol, '-') AS INTEGER) AS protocol,
        TRY_CAST(NULLIF(bytes, '-') AS BIGINT) AS byt,
        TRY_CAST(NULLIF(packets, '-') AS BIGINT) AS pkt,
        year,
        month,
        _source_file
    FROM {{ ref('bronze_vpc_flowlogs') }}

    {% if is_incremental() %}
    -- Filter source records to only process partitions at or newer than max existing partition in Silver
    WHERE (year > (SELECT COALESCE(MAX(year), 1970) FROM {{ this }}))
        OR (
            year = (SELECT COALESCE(MAX(year), 1970) FROM {{ this }})
            AND month >= (SELECT COALESCE(MAX(month), 1) FROM {{ this }} WHERE year = (SELECT MAX(year) FROM {{ this }}))
        )
    {% endif %}

)

SELECT
    sp,
    dp,
    protocol,
    byt,
    pkt,
    year,
    month,
    _source_file
FROM bronze_source
