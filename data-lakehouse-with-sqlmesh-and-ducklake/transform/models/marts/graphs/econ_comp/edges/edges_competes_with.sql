MODEL (
  name graphs.econ_comp.edges_competes_with,
  kind FULL,
  description 'Countries that export similar products and are significantly dependent on those products as a part of their exports share.',
  column_descriptions (
    source_id = 'Country node ID for the larger exporter',
    target_id = 'Country node ID for the smaller exporter',
    esi = 'Economic similarity index between the two countries'
  ),
  audits (
    not_null(columns := (source_id, target_id))
  )
);

SELECT
    sn.node_id AS source_id,
    tn.node_id AS target_id,
    m.esi AS esi

FROM analytics.taoec.cc_metrics AS m

JOIN graphs.econ_comp.nodes_countries AS sn
ON m.country_id_1 = sn.country_id

JOIN graphs.econ_comp.nodes_countries AS tn
ON m.country_id_2 = tn.country_id

WHERE m.esi > 0

ORDER BY m.esi DESC
