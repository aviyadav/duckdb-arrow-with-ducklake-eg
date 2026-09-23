{% macro duckdb__drop_relation(relation) -%}
  {% call statement('drop_relation') -%}
    {% if relation.type == 'view' %}
      drop view if exists {{ relation }}
    {% else %}
      drop table if exists {{ relation }}
    {% endif %}
  {%- endcall %}
{%- endmacro %}
