# Airflow local pipeline (medallion) — instruções e novidades

Este repositório contém uma instância local do Apache Airflow em Docker com uma
pipeline Medallion (Bronze → Silver → Gold). Este README foi atualizado para
documentar as novas features implementadas: scripts separados para cada camada,
logging em JSON, verificação de qualidade de dados (DQ) e um sistema de alertas
por e‑mail (com MailHog para testes locais e opção de SMTP real).

## Architecture

### Blueprint e Components Principais

A arquitetura segue o padrão **Medallion Architecture** (camadas Bronze → Silver → Gold) com orquestração por Apache Airflow:

```
┌─────────────────────────────────────────────────────────────────────────┐
│                     Apache Airflow (Docker)                             │
│  ┌──────────────────────────────────────────────────────────────────┐   │
│  │  medallion_pipeline (DAG)                                        │   │
│  │  ├─ bronze_task      → Ingestão / API externa (JSON)             │   │
│  │  ├─ silver_task      → Transformação (Parquet particionado)      │   │
│  │  ├─ dq_check_task    → Validação de qualidade                    │   │
│  │  └─ gold_task        → Agregação final (Delta Lake)              │   │
│  └──────────────────────────────────────────────────────────────────┘   │
│                                                                         │
│  Services: Webserver + Scheduler                                        │
└─────────────────────────────────────────────────────────────────────────┘
                                    ↓
┌─────────────────────────────────────────────────────────────────────────┐
│                        Data Layers (Local Storage)                      │
│                                                                         │
│  📁 /opt/airflow/data/                                                  │
│  ├─ bronze/           ← JSON raw (Open Brewery DB)                      │
│  ├─ silver/           ← Parquet (cleaned, transformed)                  │
│  ├─ gold_delta/       ← Delta Lake (aggregated, indexed)                │
│  └─ logging/          ← JSON logs (execution metrics + DQ alerts)       │
│                                                                         │
└─────────────────────────────────────────────────────────────────────────┘
                                    ↓
┌─────────────────────────────────────────────────────────────────────────┐
│                    Observability & Alerting                             │
│                                                                         │
│  📧 Email Alerts (Airflow + SMTP)  → MailHog (local) ou SMTP real      │
│  📊 JSON Logging                   → Audit trail de execuções          │
│  🏥 Health Checks                  → Endpoint /health (webserver)      │
│                                                                         │
└─────────────────────────────────────────────────────────────────────────┘
```

### Data Flow

1. **Bronze (Ingestão)**
   - Fetch de dados da API (Open Brewery DB)
   - Armazenamento como JSON bruto em `/data/bronze/`
   - Naming: `bronze_breweries_<TIMESTAMP>.json`

2. **Silver (Transformação)**
   - Leitura de arquivos Bronze JSON
   - Limpeza, validação, casting de tipos
   - Remoção de duplicatas e valores nulos
   - Armazenamento particionado em Parquet em `/data/silver/run_<TIMESTAMP>/`

3. **DQ Check (Validação)**
   - Avaliação de regras (contagem de registros, valores nulos, ranges)
   - Geração de logs JSON com métricas
   - Trigger de alertas via e‑mail se violações encontradas

4. **Gold (Agregação)**
   - Leitura de dados Silver
   - Agregações: contagem por estado, tipo de cervejaria, etc.
   - Tentativa de escrita em Delta Lake (`/data/gold_delta/`)
   - Fallback para Parquet se Delta indisponível

### Technology Stack

| Componente | Tecnologia |
|-----------|-----------|
| **Orquestração** | Apache Airflow 2.8.0 |
| **Python** | 3.11 |
| **Storage** | Local (Parquet, JSON, Delta Lake) |
| **Pipeline Type** | Batch (scheduled) |
| **Logging** | JSON custom + Airflow logs |
| **Alertas** | SMTP (MailHog/Real) + Airflow email op |
| **Containerização** | Docker + Docker Compose |

### Estrutura de Pastas

```
airflow_home/
├─ dags/
│  ├─ medallion_pipeline_dag.py     (DAG principal)
│  └─ scripts/                      (lógica separada por camada)
│     ├─ bronze.py
│     ├─ silver.py
│     ├─ gold.py
│     ├─ dq.py
│     ├─ logging.py
│     └─ alert.py
├─ data/
│  ├─ bronze/                       (JSON bruto)
│  ├─ silver/                       (Parquet transformado)
│  ├─ gold_delta/                   (Delta Lake)
│  └─ logging/                      (JSON logs)
└─ logs/                            (Airflow task logs)

config/                             (Configurações customizadas)
plugins/                            (Plugins Airflow customizados)
```

Resumo rápido
- Orquestração: Airflow (webserver + scheduler) via `docker-compose`.
- Pipeline: `medallion_pipeline` (tasks: bronze_task, silver_task, dq_check_task, gold_task).
- Scripts: implementações extraídas para `airflow_home/dags/scripts/` — `bronze.py`,
  `silver.py`, `gold.py`, `logging.py`, `dq.py`, `alert.py`.
- Logging: eventos de execução e métricas DQ escritos como JSON em
  `/opt/airflow/data/logging` (um arquivo JSON por evento).
- Alertas: envio de e‑mail em caso de falhas/DQ via Airflow `send_email` com
  fallback por `smtplib`. Para testes locais, MailHog está integrado ao
  `docker-compose`.

Arquivos principais criados/alterados
- `airflow_home/dags/medallion_pipeline_dag.py` — DAG que delega lógica aos scripts.
- `airflow_home/dags/scripts/bronze.py` — fetch e gravação Bronze (JSON).
- `airflow_home/dags/scripts/silver.py` — transformação Silver (Parquet particionado).
- `airflow_home/dags/scripts/gold.py` — agregação Gold e tentativa de escrita Delta.
- `airflow_home/dags/scripts/logging.py` — helper para gravar eventos JSON em
  `/opt/airflow/data/logging`.
- `airflow_home/dags/scripts/dq.py` — avaliador de regras de qualidade e gerador
  de alertas.
- `airflow_home/dags/scripts/alert.py` — helper de envio de e‑mail (Airflow + SMTP
  fallback).
- `docker-compose.yml` — adicionado serviço `mailhog` e variáveis SMTP de exemplo.

Como rodar (modo rápido)
1. Subir os containers:

```powershell
docker-compose up -d
```

2. Acesse a UI do Airflow: http://localhost:8080
3. Para ver as mensagens capturadas pelo MailHog (teste local):
   - UI MailHog: http://localhost:8025
   - API MailHog: http://localhost:8025/api/v2/messages

Testes manuais úteis (PowerShell)
- Listar DAGs:

```powershell
docker-compose run --rm airflow-webserver airflow dags list
```

- Executar tasks isoladas (útil para debug):

```powershell
# executar bronze (gera /opt/airflow/data/bronze/*.json)
docker-compose run --rm airflow-webserver airflow tasks test medallion_pipeline bronze_task 2026-01-18

# executar silver (gera /opt/airflow/data/silver/run_<timestamp>)
docker-compose run --rm airflow-webserver airflow tasks test medallion_pipeline silver_task 2026-01-18

# executar dq_check (avaliador de qualidade e envio de alerta se necessário)
docker-compose run --rm airflow-webserver airflow tasks test medallion_pipeline dq_check_task 2026-01-18

# executar gold
docker-compose run --rm airflow-webserver airflow tasks test medallion_pipeline gold_task 2026-01-18
```

Observação: ao usar `airflow tasks test` na task `dq_check_task` sem fornecer
`silver_path`, o checker pode não localizar o log correto — o fluxo end‑to‑end
(bronze → silver → dq_check) em uma mesma execução é a forma mais realista de
testar.

Configuração de SMTP (para enviar e‑mails a caixas reais)

Por padrão este repositório está configurado para usar MailHog (local) para
testes. Para enviar e‑mails para contas reais (Hotmail, Gmail, etc.) você deve
fornecer credenciais SMTP de um provedor confiável (SendGrid, Mailgun, SES,
ou SMTP do seu domínio). Existem duas opções:

1) Usar um serviço de envio (recomendado)
   - Crie/obtenha credenciais no provedor (ex.: SendGrid API key ou Mailgun SMTP).
   - Atualize `docker-compose.yml` nas seções `airflow-webserver` e
     `airflow-scheduler` com as variáveis abaixo (exemplo SendGrid):

```yaml
environment:
  - AIRFLOW__SMTP__SMTP_HOST=smtp.sendgrid.net
  - AIRFLOW__SMTP__SMTP_PORT=587
  - AIRFLOW__SMTP__SMTP_MAIL_FROM=no-reply@seudominio.com
  - AIRFLOW__SMTP__SMTP_USER=apikey
  - AIRFLOW__SMTP__SMTP_PASSWORD=<SUA_SENDGRID_API_KEY>
  - AIRFLOW__SMTP__SMTP_STARTTLS=True
  - AIRFLOW__SMTP__SMTP_SSL=False

  # fallback usado por scripts/alert.py (opcional)
  - ALERT_SMTP_HOST=smtp.sendgrid.net
  - ALERT_SMTP_PORT=587
  - ALERT_SMTP_USER=apikey
  - ALERT_SMTP_PASSWORD=<SUA_SENDGRID_API_KEY>
  - ALERT_SMTP_FROM=no-reply@seudominio.com
  - ALERT_SMTP_USE_TLS=True
```

2) Usar um serviço de inbox de testes (Mailtrap, Ethereal)
   - Crie conta no serviço, obtenha credenciais SMTP e use no compose como
     acima. Esses serviços não entregam à internet, mas permitem ver a mensagem
     em uma inbox web (útil para validação sem afetar destinatários reais).

Rebuild / dependências
- Se você pretende usar Delta Lake (`deltalake`) ou manipular Parquet com
  `pandas`/`pyarrow` dentro do container, certifique-se de que `requirements.txt`
  contém as dependências necessárias e reconstrua a imagem:

```powershell
docker-compose build --no-cache
docker-compose up -d
```

