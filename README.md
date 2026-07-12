# Dual-Mode Agentic RAG Chatbot — Northwind Gadgets

> Work in progress. This README currently covers the data ingestion and
> retrieval core (RAG + text-to-SQL). API layer, streaming, and frontend
> are being added next.

## What's built so far

- **`ingest/ingest_docs.py`** — parses the 5 policy PDFs, splits them into
  section-aware chunks (handles both numbered headers like "1. Returns" and
  plain Title Case headers like "Order Tracking"), embeds them with OpenAI
  `text-embedding-3-small`, and stores them in a persistent Chroma collection.
- **`ingest/load_orders.py`** — loads `orders.csv` (200 rows) into a local
  SQLite DB. This table is deliberately **not** embedded — the SQL tool
  queries it directly, per the assignment spec.
- **`app/rag.py`** — retrieval + answer generation for document questions.
  Retrieves top-4 chunks, and if the best match is below a similarity
  threshold, returns a fallback instead of forcing an answer. Otherwise asks
  the LLM to answer using only the retrieved excerpts, with citation markers
  tied back to source file + section.
- **`app/sql_tool.py`** — text-to-SQL. The LLM is given the exact schema
  (never the data) and a fixed "current date" anchor (2026-06-15, per the
  assessment brief) for relative date questions. Generated SQL is validated
  before execution: must be a single `SELECT`, no write/DDL keywords, and
  every identifier used must exist in the real schema (catches hallucinated
  columns). Runs against a read-only SQLite connection.

## Why these choices

- **Chroma over Pinecone/pgvector**: zero external infra to stand up over a
  weekend, persists to disk, good enough for 26 chunks. Would reconsider for
  a larger corpus or multi-tenant setup.
- **Section-aware chunking over fixed-size windows**: these are short policy
  docs where a whole section (e.g. "Refund Processing") is the natural unit
  of a citable fact. Fixed-size windows would sometimes split a policy rule
  across two chunks and lose the citation's meaning. Falls back to a sliding
  window only if a section is unusually long.
- **Schema-only SQL generation**: the model never sees the actual row data,
  only column names/types, which keeps sensitive data out of the prompt and
  makes the hallucinated-column check meaningful (if the model has never
  seen a `refund_reason` column, it shouldn't be inventing one).
- **Distance threshold fallback in RAG**: prevents the LLM from confidently
  answering from irrelevant chunks when a question is genuinely out of
  scope (e.g. general knowledge questions).

## Try it yourself

```bash
pip install -r requirements.txt
cp .env.example .env   # add your OPENAI_API_KEY

python ingest/load_orders.py     # builds data/orders.db
python ingest/ingest_docs.py     # builds data/chroma/

python scripts/test_rag.py       # proves RAG + citations work
python scripts/test_sql.py       # proves text-to-SQL + guardrails work
```

## Known limitations (so far)

- Column-hallucination guard is a regex-based heuristic, not a full SQL
  parser — good enough for this schema's complexity, would need a real
  parser (e.g. `sqlglot`) for a more complex schema.
- No conversation memory yet — each question is answered independently.
- Router (deciding RAG vs SQL vs both) and the FastAPI/streaming layer are
  not built yet — next step.

## Next up
FastAPI backend with streaming, the router/agent layer, Next.js chat UI,
Docker, deployment.
