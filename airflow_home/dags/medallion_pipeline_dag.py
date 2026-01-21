from __future__ import annotations

import json
import csv
from datetime import datetime, timedelta
from typing import List, Dict, Any

from airflow.decorators import dag, task
from airflow.utils.dates import days_ago


def _notify_on_failure(context: dict) -> None:
    """Callback to notify when a task fails.

    Tries to send an email with basic info. Any error while sending is logged and
    swallowed so it doesn't mask the original task failure.
    """
    try:
        from airflow.utils.email import send_email

        ti = context.get("task_instance")
        dag = context.get("dag")
        dag_id = dag.dag_id if dag is not None else context.get("dag_id")
        task_id = ti.task_id if ti is not None else context.get("task_id")
        run_id = context.get("run_id") or (ti.run_id if ti is not None else "")
        log_url = ti.log_url if ti is not None else ""

        subject = f"[Airflow] Failure: {dag_id}.{task_id}"
        html = f"""
        <p>Task <b>{task_id}</b> in DAG <b>{dag_id}</b> failed.</p>
        <p>Run id: {run_id}</p>
        <p><a href=\"{log_url}\">View logs in Airflow</a></p>
        """

        # recipient list: change to your real email
        send_email(to=["matheusneryds@gmail.com"], subject=subject, html_content=html)
    except Exception:
        import logging

        logging.exception("Error sending failure email")


DEFAULT_ARGS = {
    "owner": "airflow",
    "depends_on_past": False,
    "retries":2,
    "retry_delay": timedelta(minutes=5),
    "email": ["matheusneryds@gmail.com"],
    "email_on_failure": True,
    "on_failure_callback": _notify_on_failure
}


@dag(
    dag_id="medallion_pipeline", 
    start_date=days_ago(1), 
    schedule_interval=timedelta(days=1), 
    default_args=DEFAULT_ARGS, 
    catchup=False
    )
def medallion_pipeline():
    """Simple medallion pipeline: bronze -> silver -> gold.

    - bronze: fetch raw data from OpenBreweryDB and save JSON raw
    - silver: clean / normalize selected fields
    - gold: aggregate (count breweries per state) and save CSV
    """

    @task()
    def bronze_task(per_page: int = 50, max_pages: int = 5) -> str:
        # delegate to scripts/bronze.py to keep DAG lightweight
        # import inside task to avoid heavy imports at parse time
        from scripts.bronze import run as bronze_run

        return bronze_run(per_page=per_page, max_pages=max_pages)

    @task()
    def silver_task(bronze_path: str) -> str:
        """Transform raw JSON into Parquet partitioned by state.

        - selects a subset of fields
        - normalizes state (upper-case)
        - writes a partitioned Parquet dataset under /opt/airflow/data/silver
        Returns the path to the silver folder (dataset root).
        """
        # delegate to scripts/silver.py
        from scripts.silver import run as silver_run

        return silver_run(bronze_path)

    @task()
    def gold_task(silver_path: str) -> str:
        """Read silver parquet dataset for this run, aggregate counts per brewery_type and state,
        and write into a Delta Lake table incrementally (partitioned by run_date).

        If the `deltalake` library isn't available or writing fails, falls back to writing a
        parquet file under `/opt/airflow/data/gold_fallback`.
        """
        # delegate to scripts/gold.py
        from scripts.gold import run as gold_run

        return gold_run(silver_path)

    @task()
    def dq_check_task(silver_path: str) -> dict:
        """Run data-quality checks on the silver output and send alerts if needed.

        This task delegates to `scripts.dq.run`. By default it will send email
        alerts but will not fail the DAG. You can change behavior by editing
        scripts/dq.py or by changing the task to pass fail_on_error=True.
        """
        from typing import List
        from scripts.dq import run as dq_run

        # recipients: try to use DEFAULT_ARGS email if present via env; otherwise empty
        recipients: List[str] = DEFAULT_ARGS.get("email") or []

        return dq_run(silver_path, recipients=recipients, thresholds={})

    @task()
    def test_email_alert_task() -> str:
        """Test task to validate email alert system.
        
        This task intentionally fails to test that email alerts are working.
        Check your email at https://ethereal.email/messages to see the alert.
        
        To disable this test, comment out or remove this task and its call below.
        """
        raise Exception("TEST: Intentional error to validate email alert system!")

    # Orchestration: bronze -> silver -> gold
    bronze_path = bronze_task()
    silver_path = silver_task(bronze_path)
    # insert DQ check between silver and gold
    dq_result = dq_check_task(silver_path)
    gold_path = gold_task(silver_path)
    
    # Test email alerts (comment out after validation)
    test_alert = test_email_alert_task()


    return {}


dag = medallion_pipeline()
