#!/bin/sh
set -e

echo "Building orders.db from orders.csv..."
python ingest/load_orders.py

echo "Building Chroma vector store from policy docs..."
python ingest/ingest_docs.py

echo "Starting FastAPI server..."
exec uvicorn app.main:app --host 0.0.0.0 --port "${PORT:-8000}"
