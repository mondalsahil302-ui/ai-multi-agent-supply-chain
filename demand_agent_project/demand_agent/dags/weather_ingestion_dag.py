"""Airflow DAG for scheduled daily Open-Meteo weather ingestion."""
from datetime import datetime, timedelta

try:
    from airflow import DAG
    from airflow.operators.python import PythonOperator
    AIRFLOW_AVAILABLE = True
except ImportError:
    AIRFLOW_AVAILABLE = False


def execute_weather_ingestion():
    from demand_agent.config import get_settings
    from demand_agent.db import get_db
    from demand_agent.ingestion.pipeline import ingest_weather_forecasts

    s = get_settings()
    db = get_db(s)
    result = ingest_weather_forecasts(db, s)
    print("Weather ingestion result:", result)
    return result


if AIRFLOW_AVAILABLE:
    default_args = {
        "owner": "demand_agent",
        "depends_on_past": False,
        "email_on_failure": False,
        "email_on_retry": False,
        "retries": 2,
        "retry_delay": timedelta(minutes=5),
    }

    dag = DAG(
        dag_id="demand_agent_weather_ingestion",
        default_args=default_args,
        description="Daily Open-Meteo weather forecast ingestion with quarantine and idempotency",
        schedule_interval="0 2 * * *",  # 02:00 AM daily
        start_date=datetime(2026, 1, 1),
        catchup=False,
        tags=["demand_agent", "weather", "ingestion"],
    )

    task_ingest_weather = PythonOperator(
        task_id="ingest_weather_forecasts",
        python_callable=execute_weather_ingestion,
        dag=dag,
    )
