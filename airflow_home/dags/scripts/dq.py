from __future__ import annotations

import json
import os
from typing import Any, Dict, List, Optional

from datetime import datetime

from scripts.alert import send_email


def _find_silver_log(silver_path: str) -> Optional[str]:
    """Find the most recent logging JSON file whose metrics.silver_path equals the given path."""
    log_dir = "/opt/airflow/data/logging"
    if not os.path.isdir(log_dir):
        return None
    candidates: List[str] = []
    for name in os.listdir(log_dir):
        if not name.endswith(".json"):
            continue
        path = os.path.join(log_dir, name)
        try:
            with open(path, "r", encoding="utf-8") as fh:
                data = json.load(fh)
            metrics = data.get("metrics", {})
            if metrics.get("silver_path") == silver_path and data.get("stage") == "silver":
                candidates.append(path)
        except Exception:
            continue

    if not candidates:
        return None
    # return most recent by filename timestamp
    candidates.sort()
    return candidates[-1]


def _evaluate_rules(metrics: Dict[str, Any], thresholds: Dict[str, Any]) -> List[str]:
    issues: List[str] = []
    row_count = int(metrics.get("row_count", 0))
    if row_count == 0:
        issues.append("silver dataset is empty (row_count=0)")
        return issues

    min_rows = int(thresholds.get("min_rows", 50))
    if row_count < min_rows:
        issues.append(f"row_count {row_count} below min_rows {min_rows}")

    # example: monitor website_url missing percentage
    null_counts = metrics.get("null_counts", {})
    missing_website = int(null_counts.get("website_url", 0))
    missing_pct = missing_website / max(1, row_count)
    max_missing_pct = float(thresholds.get("max_missing_website_pct", 0.2))
    if missing_pct > max_missing_pct:
        issues.append(f"website_url missing {missing_pct:.1%} > {max_missing_pct:.1%}")

    # example: low cardinality of states
    distinct_states = int(metrics.get("distinct_states", 0))
    min_states = int(thresholds.get("min_states", 5))
    if distinct_states < min_states:
        issues.append(f"distinct_states {distinct_states} below min_states {min_states}")

    return issues


def run(
        silver_path: str,
        recipients: Optional[List[str]] = None,
        thresholds: Optional[Dict[str, Any]] = None,
        fail_on_error: bool = False,
        ) -> Dict[str, Any]:
    """Run data-quality checks for the given silver_path.

    - recipients: list of emails to notify (if None, uses DEFAULT from env or Airflow DEFAULT_ARGS)
    - thresholds: overrides for rule thresholds
    - fail_on_error: if True, raises Exception when issues found

    Returns a dict: {status: 'ok'|'warn'|'fail', 'issues': [...]}.
    """
    thresholds = thresholds or {}
    recipients = recipients or []

    log_path = _find_silver_log(silver_path)
    if log_path is None:
        # if we can't find a log, warn and optionally fail
        msg = f"No silver log found for path {silver_path}"
        if recipients:
            try:
                send_email(recipients, f"DQ: missing log for {silver_path}", msg)
            except Exception:
                pass
        if fail_on_error:
            raise RuntimeError(msg)
        return {"status": "warn", "issues": [msg]}

    with open(log_path, "r", encoding="utf-8") as fh:
        data = json.load(fh)
    metrics = data.get("metrics", {})

    issues = _evaluate_rules(metrics, thresholds)
    if not issues:
        return {"status": "ok", "issues": []}

    # build email body
    subject = f"DQ Alert: {len(issues)} issue(s) for silver_path"
    html = f"<p>Found {len(issues)} data-quality issue(s) for <b>{silver_path}</b></p>"
    html += "<ul>"
    for it in issues:
        html += f"<li>{it}</li>"
    html += "</ul>"
    html += f"<pre>{json.dumps(metrics, indent=2, ensure_ascii=False)}</pre>"

    if recipients:
        try:
            send_email(recipients, subject, html)
        except Exception:
            # swallow errors to not mask pipeline unless requested
            pass

    if fail_on_error:
        raise RuntimeError("; ".join(issues))

    return {"status": "warn", "issues": issues}
