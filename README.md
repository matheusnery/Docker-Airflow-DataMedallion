# Airflow local pipeline (medallion)

This repository contains a local Apache Airflow instance in Docker with a
Medallion pipeline (Bronze → Silver → Gold).

## Architecture

### Blueprint and Main Components

The architecture follows the **Medallion Architecture** pattern (Bronze → Silver → Gold layers) with orchestration by Apache Airflow:

```
┌─────────────────────────────────────────────────────────────────────────┐
│                     Apache Airflow (Docker)                             │
│  ┌──────────────────────────────────────────────────────────────────┐   │
│  │  medallion_pipeline (DAG)                                        │   │
│  │  ├─ bronze_task      → Ingestion / External API (JSON)           │   │
│  │  ├─ silver_task      → Transformation (Partitioned Parquet)      │   │
│  │  ├─ dq_check_task    → Quality validation                        │   │
│  │  └─ gold_task        → Final aggregation (Delta Lake)            │   │
│  └──────────────────────────────────────────────────────────────────┘   │
│                                                                         │
│  Services: Webserver + Scheduler                                        │
└─────────────────────────────────────────────────────────────────────────┘
                                    ↓
┌─────────────────────────────────────────────────────────────────────────┐
│                        Data Layers (Local Storage)                      │
│                                                                         │
│  📁 /opt/airflow/data/                                                  │
│  ├─ bronze/           ← Raw JSON (Open Brewery DB)                      │
│  ├─ silver/           ← Parquet (cleaned, transformed)                  │
│  ├─ gold_delta/       ← Delta Lake (aggregated, indexed)                │
│  └─ logging/          ← JSON logs (execution metrics + DQ alerts)       │
│                                                                         │
└─────────────────────────────────────────────────────────────────────────┘
                                    ↓
┌─────────────────────────────────────────────────────────────────────────┐
│                    Observability & Alerting                             │
│                                                                         │
│  📧 Email Alerts (Airflow + SMTP)  → Ethereal Email (testing)          │
│  📊 JSON Logging                   → Execution audit trail              │
│  🏥 Health Checks                  → /health endpoint (webserver)       │
│                                                                         │
└─────────────────────────────────────────────────────────────────────────┘
```

### Data Flow

1. **Bronze (Ingestion)**
   - Fetch data from API (Open Brewery DB)
   - Store as raw JSON in `/data/bronze/`
   - Naming: `bronze_breweries_<TIMESTAMP>.json`

2. **Silver (Transformation)**
   - Read Bronze JSON files
   - Cleaning, validation, type casting
   - Duplicate and null value removal
   - Partitioned storage in Parquet at `/data/silver/run_<TIMESTAMP>/`

3. **DQ Check (Validation)**
   - Evaluate rules (record count, null values, ranges)
   - Generate JSON logs with metrics
   - Trigger email alerts if violations are found

4. **Gold (Aggregation)**
   - Read Silver data
   - Aggregations: count by state, brewery type, etc.
   - Attempt to write to Delta Lake (`/data/gold_delta/`)
   - Fallback to Parquet if Delta is unavailable

### Technology Stack

| Component | Technology |
|-----------|-----------|
| **Orchestration** | Apache Airflow 2.8.0 |
| **Python** | 3.11 |
| **Storage** | Local (Parquet, JSON, Delta Lake) |
| **Pipeline Type** | Batch (scheduled) |
| **Logging** | Custom JSON + Airflow logs |
| **Alerts** | SMTP (MailHog/Real) + Airflow email op |
| **Containerization** | Docker + Docker Compose |

### Folder Structure

```
airflow_home/
├─ dags/
│  ├─ medallion_pipeline_dag.py     (Main DAG)
│  └─ scripts/                      (Logic separated by layer)
│     ├─ bronze.py
│     ├─ silver.py
│     ├─ gold.py
│     ├─ dq.py
│     ├─ logging.py
│     └─ alert.py
├─ data/
│  ├─ bronze/                       (Raw JSON)
│  ├─ silver/                       (Transformed Parquet)
│  ├─ gold_delta/                   (Delta Lake)
│  └─ logging/                      (JSON logs)
└─ logs/                            (Airflow task logs)

config/                             (Custom configurations)
plugins/                            (Custom Airflow plugins)
```

Quick Summary
- Orchestration: Airflow (webserver + scheduler) via `docker-compose`.
- Pipeline: `medallion_pipeline` (tasks: bronze_task, silver_task, dq_check_task, gold_task).
- Scripts: implementations extracted to `airflow_home/dags/scripts/` - `bronze.py`,
  `silver.py`, `gold.py`, `logging.py`, `dq.py`, `alert.py`.
- Logging: execution events and DQ metrics written as JSON in
  `/opt/airflow/data/logging` (one JSON file per event).
- Alerts: email sending in case of failures/DQ via Airflow `send_email` using
  Ethereal Email for testing (configured in docker-compose.yml).

Main created/modified files
- `airflow_home/dags/medallion_pipeline_dag.py` - DAG that delegates logic to scripts.
- `airflow_home/dags/scripts/bronze.py` - fetch and Bronze writing (JSON).
- `airflow_home/dags/scripts/silver.py` - Silver transformation (partitioned Parquet).
- `airflow_home/dags/scripts/gold.py` - Gold aggregation and Delta write attempt.
- `airflow_home/dags/scripts/logging.py` - helper to write JSON events in
  `/opt/airflow/data/logging`.
- `airflow_home/dags/scripts/dq.py` - quality rules evaluator and alert
  generator.
- `airflow_home/dags/scripts/alert.py` - email sending helper using Airflow's
  built-in SMTP.
- `docker-compose.yml` - configured with Ethereal Email SMTP for testing.

How to run (quick mode)
1. Start the containers:

```powershell
docker-compose up -d
```

2. Access Airflow UI: http://localhost:8080
3. Check email alerts at Ethereal Email viewer (check your credentials)

Useful manual tests (PowerShell)
- List DAGs:

```powershell
docker-compose run --rm airflow-webserver airflow dags list
```

- Run isolated tasks (useful for debugging):

```powershell
# run bronze (generates /opt/airflow/data/bronze/*.json)
docker-compose run --rm airflow-webserver airflow tasks test medallion_pipeline bronze_task 2026-01-18

# run silver (generates /opt/airflow/data/silver/run_<timestamp>)
docker-compose run --rm airflow-webserver airflow tasks test medallion_pipeline silver_task 2026-01-18

# run dq_check (quality evaluator and alert sending if needed)
docker-compose run --rm airflow-webserver airflow tasks test medallion_pipeline dq_check_task 2026-01-18

# run gold
docker-compose run --rm airflow-webserver airflow tasks test medallion_pipeline gold_task 2026-01-18
```

Note: when using `airflow tasks test` on the `dq_check_task` task without providing
`silver_path`, the checker may not locate the correct log. The end-to-end flow
(bronze → silver → dq_check) in the same execution is the most realistic way to
test.

SMTP Configuration (to send emails to real inboxes)

By default this repository is configured to use Ethereal Email for
testing. To send emails to real accounts (Hotmail, Gmail, etc.) you must
provide SMTP credentials from a trusted provider (SendGrid, Mailgun, SES,
or your domain's SMTP). There are two options:

1) Use a sending service (recommended)
   - Create/obtain credentials from the provider (e.g., SendGrid API key or Mailgun SMTP).
   - Update `docker-compose.yml` in the `airflow-webserver` and
     `airflow-scheduler` sections with the variables below (SendGrid example):

```yaml
environment:
  - AIRFLOW__SMTP__SMTP_HOST=smtp.sendgrid.net
  - AIRFLOW__SMTP__SMTP_PORT=587
  - AIRFLOW__SMTP__SMTP_MAIL_FROM=no-reply@yourdomain.com
  - AIRFLOW__SMTP__SMTP_USER=apikey
  - AIRFLOW__SMTP__SMTP_PASSWORD=<YOUR_SENDGRID_API_KEY>
  - AIRFLOW__SMTP__SMTP_STARTTLS=True
  - AIRFLOW__SMTP__SMTP_SSL=False
```

2) Use a test inbox service (Mailtrap, Ethereal)
   - Already configured with Ethereal Email. View messages at https://ethereal.email
   - Or create account on another service, obtain SMTP credentials and update docker-compose.yml
     as shown above. These services don't deliver to the internet, but allow you to see the message
     in a web inbox (useful for validation without affecting real recipients).

Rebuild / dependencies
- If you plan to use Delta Lake (`deltalake`) or manipulate Parquet with
  `pandas`/`pyarrow` inside the container, make sure `requirements.txt`
  contains the necessary dependencies and rebuild the image:

```powershell
docker-compose build --no-cache
docker-compose up -d
```

