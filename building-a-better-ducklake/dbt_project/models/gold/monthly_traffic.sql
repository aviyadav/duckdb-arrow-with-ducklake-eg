{{ config(materialized='table') }}

SELECT
    year,
    month,
    COUNT(*) AS total_flows,
    ROUND(SUM(COALESCE(byt, 0)) / 1024.0 / 1024.0 / 1024.0, 2) AS total_gb,
    ROUND(SUM(pkt) / 1000000.0, 2) AS total_million_packets
FROM {{ ref('silver_vpc_flowlogs') }}
GROUP BY year, month
ORDER BY year DESC, month DESC
