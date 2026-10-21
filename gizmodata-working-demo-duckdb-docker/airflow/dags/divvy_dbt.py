"""Run the dbt project against GizmoSQL on a daily schedule.

Targets Airflow 3.x. The `divvy_dbt` directory is bind-mounted into the
scheduler at ${DIVVY_DBT_DIR:-/opt/airflow/divvy_dbt}.
"""
import os

import pendulum
from airflow.providers.standard.operators.bash import BashOperator
from airflow.sdk import DAG

DBT_DIR = os.environ.get("DIVVY_DBT_DIR", "/opt/airflow/divvy_dbt")
DBT_BIN = os.environ.get("DBT_BIN", "dbt")
DBT = f"cd {DBT_DIR} && {DBT_BIN} --no-use-colors"

with DAG(
    dag_id="divvy_dbt",
    schedule="@daily",
    start_date=pendulum.datetime(2026, 10, 1, tz="UTC"),
    catchup=False,
    tags=["gizmosql", "dbt"],
) as dag:
    dbt_run = BashOperator(task_id="dbt_run", bash_command=f"{DBT} run --profiles-dir .")
    dbt_test = BashOperator(task_id="dbt_test", bash_command=f"{DBT} test --profiles-dir .")

    dbt_run >> dbt_test
