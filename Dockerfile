# Backend: FastAPI + agent (RAG + text-to-SQL)
FROM python:3.12-slim

WORKDIR /app

# System deps needed to build any C-extension wheels not available prebuilt
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY app/ ./app/
COPY ingest/ ./ingest/
COPY data/docs/ ./data/docs/
COPY data/orders.csv ./data/orders.csv
COPY docker-entrypoint.sh .
RUN chmod +x docker-entrypoint.sh

EXPOSE 8000

# Ingestion (building the vector store + SQLite DB) runs at container
# startup rather than image build time, so OPENAI_API_KEY only ever exists
# as a runtime environment variable, never baked into an image layer.
ENTRYPOINT ["./docker-entrypoint.sh"]
