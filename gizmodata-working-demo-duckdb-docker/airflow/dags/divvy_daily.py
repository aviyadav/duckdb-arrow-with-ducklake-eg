"""Daily Divvy pipeline: run SQL on GizmoSQL via the ADBC driver.

Credentials are stored in an Airflow connection named `gizmosql_default`,
not in code. Targets Airflow 3.x.
"""
import pendulum
from airflow.decorators import dag, task
from airflow.hooks.base import BaseHook


@dag(schedule="@daily", start_date=pendulum.datetime(2026, 1, 1), catchup=False,
     tags=["gizmosql"])
def divvy_daily():
    @task
    def run_sql(sql: str):
        from adbc_driver_gizmosql import dbapi as gizmosql
        c = BaseHook.get_connection("gizmosql_default")  # creds live in Airflow
        with gizmosql.connect(
            f"gizmosql://{c.host}:{c.port}",
            username=c.login,
            password=c.password,
            tls_skip_verify=True,
        ) as conn, conn.cursor() as cur:
            cur.execute(sql)

    raw = run_sql.override(task_id="load_raw")(
        "CREATE OR REPLACE VIEW raw_trips AS "
        "SELECT * FROM read_csv('/opt/gizmosql/data/*.csv', "
        "union_by_name = true)")
    agg = run_sql.override(task_id="station_daily")(
        "CREATE OR REPLACE TABLE station_daily AS "
        "SELECT start_station_name, started_at::date d, count(*) n "
        "FROM raw_trips GROUP BY ALL")
    raw >> agg


divvy_daily()
