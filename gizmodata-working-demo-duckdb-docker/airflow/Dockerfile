# Airflow image for the GizmoSQL / DuckDB demo.
# Extends the official image with the Arrow Flight SQL (ADBC) driver used by
# the Python DAG, plus dbt for the dbt DAG.
FROM apache/airflow:3.1.0-python3.12

USER root
RUN apt-get update \
    && apt-get install -y --no-install-recommends git \
    && rm -rf /var/lib/apt/lists/*
USER airflow

# ADBC GizmoSQL driver: lets a Python task speak Arrow Flight SQL.
RUN pip install --no-cache-dir adbc-driver-gizmosql

# dbt lives in its own virtualenv so its dependency tree can never
# conflict with the pinned Airflow environment.
RUN python -m venv /home/airflow/dbt-venv \
    && /home/airflow/dbt-venv/bin/pip install --no-cache-dir --upgrade pip \
    && /home/airflow/dbt-venv/bin/pip install --no-cache-dir dbt-core dbt-gizmosql

ENV DBT_BIN=/home/airflow/dbt-venv/bin/dbt
