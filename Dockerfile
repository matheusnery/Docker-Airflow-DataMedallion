FROM apache/airflow:2.8.0-python3.11

USER root

# Instalar dependências do sistema
RUN apt-get update && apt-get install -y \
    curl \
    && rm -rf /var/lib/apt/lists/*

USER airflow

# Instalar dependências Python
COPY requirements.txt /requirements.txt
RUN pip install --no-cache-dir -r /requirements.txt

# Definir diretório de trabalho
WORKDIR /opt/airflow