"""Alert helper: send alerts via Airflow email or direct SMTP fallback.

This module provides a simple `send_email` function that prefers to call
Airflow's `send_email` (so SMTP settings from Airflow are respected). If
Airflow isn't available (e.g., script run outside Airflow), it falls back to
sending via smtplib using environment variables.

Environment variables used for fallback SMTP:
- ALERT_SMTP_HOST, ALERT_SMTP_PORT, ALERT_SMTP_USER, ALERT_SMTP_PASSWORD,
- ALERT_SMTP_FROM, ALERT_SMTP_USE_TLS (true/false)
"""
from __future__ import annotations

import os
import smtplib
from email.message import EmailMessage
from typing import Sequence


def _send_via_smtplib(to: Sequence[str], subject: str, html: str, sender: str | None = None) -> None:
    host = os.environ.get("ALERT_SMTP_HOST")
    port = int(os.environ.get("ALERT_SMTP_PORT", "25"))
    user = os.environ.get("ALERT_SMTP_USER")
    password = os.environ.get("ALERT_SMTP_PASSWORD")
    use_tls = os.environ.get("ALERT_SMTP_USE_TLS", "false").lower() in ("1", "true", "yes")

    if sender is None:
        sender = os.environ.get("ALERT_SMTP_FROM", "airflow@example.com")

    msg = EmailMessage()
    msg["From"] = sender
    msg["To"] = ", ".join(to)
    msg["Subject"] = subject
    msg.set_content(html, subtype="html")

    if not host:
        raise RuntimeError("No SMTP host configured for alert fallback (ALERT_SMTP_HOST)")

    s = smtplib.SMTP(host, port, timeout=10)
    try:
        if use_tls:
            s.starttls()
        if user and password:
            s.login(user, password)
        s.send_message(msg)
    finally:
        s.quit()


def send_email(to: Sequence[str], subject: str, html: str) -> None:
    """Send email preferring Airflow's send_email helper; fallback to SMTP."""
    try:
        # try to use Airflow helper when available (must be running inside Airflow)
        from airflow.utils.email import send_email as airflow_send

        # airflow_send accepts to (str or list) and html_content
        airflow_send(to=to, subject=subject, html_content=html)
        return
    except Exception:
        # fallback
        _send_via_smtplib(to, subject, html)
