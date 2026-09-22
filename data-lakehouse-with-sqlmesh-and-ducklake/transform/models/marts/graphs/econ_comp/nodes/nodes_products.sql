MODEL (
  name graphs.econ_comp.nodes_products,
  kind FULL,
  description 'Nodes for products traded by countries in the Economic Competition Network.',
  column_descriptions (
    node_id = 'Unique numerical node ID from a shared sequence',
    product_id = 'Numeric product ID',
    product_level = 'Level of the product in the classification hierarchy',
    product_name = 'Product name',
    product_name_short = 'Short product name',
    product_id_hierarchy = 'Product hierarchy as a path of product IDs'
  ),
  audits (
    not_null(columns := (
      node_id, product_id, product_level, product_name, product_name_short,
      product_id_hierarchy, show_feasibility, natural_resource
    )),
    unique_values(columns := (node_id))
  )
);

WITH node_meta AS (
    SELECT max(node_id) + 1 AS start_node_id
    FROM graphs.econ_comp.nodes_countries
)
SELECT
    n.start_node_id + row_number() OVER () AS node_id,
    product_id,
    product_hs92_code,
    product_level,
    product_name,
    product_name_short,
    product_id_hierarchy,
    show_feasibility,
    natural_resource,
    green_product
FROM
    stage.taoec.hs92_products,
    node_meta AS n
WHERE
    product_id IN (
        SELECT product_id
        FROM analytics.taoec.competing_countries_products
    )
