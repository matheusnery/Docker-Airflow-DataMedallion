from __future__ import annotations

from typing import Sequence


def send_email(to: Sequence[str], subject: str, html: str) -> None:
    """Send email using Airflow's send_email helper."""
    try:
        from airflow.utils.email import send_email as airflow_send
        
        airflow_send(to=to, subject=subject, html_content=html)
    except Exception as e:
        import logging
        logging.exception(f"Failed to send email: {e}")
        raise

