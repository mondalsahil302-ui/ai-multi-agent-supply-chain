"""Daily Airflow entry point for weather history and forecast ingestion."""

from datetime import timedelta

import pendulum
from airflow import DAG
from airflow.operators.python import PythonOperator

from demand_ingestion.config import get_settings
from demand_ingestion.database.mongodb import MongoDatabase
from demand_ingestion.ingestion.weather_ingestion import ingest_weather
from demand_ingestion.monitoring.ingestion_logger import IngestionRunStatus

settings = get_settings()


def run_weather_ingestion() -> dict[str, object]:
    with MongoDatabase(settings) as mongo:
        result = ingest_weather(mongo, settings=settings)
    run = result["run"]
    if run.status == IngestionRunStatus.FAILED:
        raise RuntimeError(
            f"Weather ingestion run {run.ingestion_run_id} failed."
        )
    return {
        "ingestion_run_id": run.ingestion_run_id,
        "status": run.status.value,
        "failed_regions": run.failed_regions,
    }


with DAG(
    dag_id="demand_agent_weather_ingestion",
    description="Daily Open-Meteo ingestion for configured regions.",
    schedule=settings.weather_ingestion_schedule,
    start_date=pendulum.datetime(2024, 1, 1, tz=settings.default_timezone),
    catchup=False,
    max_active_runs=1,
    default_args={
        "owner": "demand-agent",
        "retries": 2,
        "retry_delay": timedelta(minutes=5),
    },
    tags=["demand-agent", "weather", "block-2"],
) as dag:
    ingest_weather_task = PythonOperator(
        task_id="ingest_weather_regions",
        python_callable=run_weather_ingestion,
    )
