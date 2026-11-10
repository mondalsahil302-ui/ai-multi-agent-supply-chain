"""Scheduled Airflow entry point for Calendarific holiday refreshes."""

from datetime import timedelta

import pendulum
from airflow import DAG
from airflow.operators.python import PythonOperator

from demand_ingestion.config import get_settings
from demand_ingestion.database.mongodb import MongoDatabase
from demand_ingestion.ingestion.festival_ingestion import ingest_festivals
from demand_ingestion.monitoring.ingestion_logger import IngestionRunStatus

settings = get_settings()


def run_festival_ingestion() -> dict[str, object]:
    with MongoDatabase(settings) as mongo:
        result = ingest_festivals(mongo, settings=settings)
    run = result["run"]
    if run.status == IngestionRunStatus.FAILED:
        raise RuntimeError(
            f"Festival ingestion run {run.ingestion_run_id} failed."
        )
    return {
        "ingestion_run_id": run.ingestion_run_id,
        "status": run.status.value,
        "successful_contexts": run.successful_contexts,
    }


with DAG(
    dag_id="demand_agent_festival_ingestion",
    description="Monthly Calendarific India and West Bengal refresh.",
    schedule=settings.festival_ingestion_schedule,
    start_date=pendulum.datetime(2024, 1, 1, tz=settings.default_timezone),
    catchup=False,
    max_active_runs=1,
    default_args={
        "owner": "demand-agent",
        "retries": 2,
        "retry_delay": timedelta(minutes=5),
    },
    tags=["demand-agent", "festivals", "block-2"],
) as dag:
    ingest_festivals_task = PythonOperator(
        task_id="ingest_festival_calendar",
        python_callable=run_festival_ingestion,
    )
