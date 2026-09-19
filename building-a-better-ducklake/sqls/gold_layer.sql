CREATE SCHEMA IF NOT EXISTS gold;

-- Pre-aggregated monthly metrics
CREATE TABLE IF NOT EXISTS gold.monthly_traffic_summary AS
SELECT
    year,
    month,
    COUNT(*) AS total_flows,
    ROUND(SUM(byt) / 1024.0 / 1024.0 / 1024.0, 2) AS total_gb,
    ROUND(SUM(pkt) / 1000000.0, 2) AS total_million_packets
FROM silver.vpc_flowlogs
GROUP BY year, month
ORDER BY year DESC, month DESC;


-- Fast dynamic view over Silver for sub-second analysis
CREATE VIEW IF NOT EXISTS gold.v_top_traffic_destinations AS
SELECT
    dstaddr,
    COUNT(*) AS connection_count,
    ROUND(SUM(byt) / 1024.0 / 1024.0, 2) AS total_mb
FROM silver.vpc_flowlogs
WHERE action = 'ACCEPT'
GROUP BY dstaddr
ORDER BY total_mb DESC;
