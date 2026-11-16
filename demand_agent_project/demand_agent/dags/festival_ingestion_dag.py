"""Airflow DAG for scheduled weekly Calendarific festival ingestion."""
from datetime import datetime, timedelta

try:
    from airflow import DAG
    from airflow.operators.python import PythonOperator
    AIRFLOW_AVAILABLE = True
except ImportError:
    AIRFLOW_AVAILABLE = False


def execute_festival_ingestion():
    from demand_agent.config import get_settings
    from demand_agent.db import get_db
    from demand_agent.ingestion.pipeline import ingest_festival_calendar

    s = get_settings()
    db = get_db(s)
    result = ingest_festival_calendar(db, s)
    print("Festival ingestion result:", result)
    return result


if AIRFLOW_AVAILABLE:
    default_args = {
        "owner": "demand_agent",
        "depends_on_past": False,
        "email_on_failure": False,
        "email_on_retry": False,
        "retries": 2,
        "retry_delay": timedelta(minutes=10),
    }

    dag = DAG(
        dag_id="demand_agent_festival_ingestion",
        default_args=default_args,
        description="Weekly Calendarific festival ingestion with quarantine and idempotency",
        schedule_interval="0 3 * * 1",  # 03:00 AM Mondays
        start_date=datetime(2026, 1, 1),
        catchup=False,
        tags=["demand_agent", "festival", "ingestion"],
    )

    task_ingest_festival = PythonOperator(
        task_id="ingest_festival_calendar",
        python_callable=execute_festival_ingestion,
        dag=dag,
    )
