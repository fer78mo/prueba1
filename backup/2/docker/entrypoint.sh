#!/usr/bin/env bash
set -Eeuo pipefail

export PYTHONUNBUFFERED=1
export PYTHONPATH=/app

# Asegura directorios montados
mkdir -p /app/data/articulos /app/data/fuentes_pdf /app/data/preguntas \
         /app/output/logs /app/output/metrics /app/output/respuestas /app/output/respuestas_txt \
         /app/output/no_resueltas /app/output/resaltados

# Arranca la API FastAPI
exec uvicorn app.api.server:app --host 0.0.0.0 --port 8000
