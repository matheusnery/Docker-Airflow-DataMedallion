"""Lightweight logging helper that writes per-run JSON records.

The function `log_event` writes a single JSON file per event under
`/opt/airflow/data/logging`. Each file contains structured metadata and a
`metrics` object. This keeps the helper dependency-free (no pandas/pyarrow)
and easy to inspect on the host.
"""
from __future__ import annotations

import json
import os
from datetime import datetime
from typing import Dict, Any, Optional


def log_event(
    stage: str,
    dag_id: str = "medallion_pipeline",
    run_id: Optional[str] = None,
    task_id: Optional[str] = None,
    metrics: Optional[Dict[str, Any]] = None,
) -> str:
    """Write a single JSON log with structured metadata and a metrics object.

    Returns the path to the JSON file written.
    """
    out_dir = "/opt/airflow/data/logging"
    os.makedirs(out_dir, exist_ok=True)

    timestamp = datetime.utcnow().strftime("%Y%m%dT%H%M%SZ")
    filename = f"log_{timestamp}_{stage}.json"
    out_path = os.path.join(out_dir, filename)

    row = {
        "ts": datetime.utcnow().isoformat(),
        "stage": stage,
        "dag_id": dag_id,
        "run_id": run_id or "",
        "task_id": task_id or "",
        "metrics": metrics or {},
    }

    with open(out_path, "w", encoding="utf-8") as fh:
        json.dump(row, fh, ensure_ascii=False, indent=2)

    return out_path
