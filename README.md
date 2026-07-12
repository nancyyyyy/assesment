# Northwind Gadgets — Dual-Mode Agentic RAG Chatbot

A support chatbot that answers questions about Northwind Gadgets using two
knowledge sources — policy/FAQ documents (via vector RAG) and an orders
database (via text-to-SQL) — and decides for itself, per question, which
source(s) to use.

**Live demo:** https://assesment-kappa-bay.vercel.app
*(first request may take ~30–50s if the backend has gone to sleep — see
Known Limitations)*

---

## Architecture

```
┌─────────────┐      SSE stream      ┌────────────────────┐
│   Next.js   │ ───────────────────► │      FastAPI        │
│  (Vercel)   │ ◄─────────────────── │     (Render)         │
└─────────────┘   tokens/tool/done   └──────────┬──────────┘
                                                 │
                                     ┌───────────┴───────────┐
                                     │   Agent (agent.py)     │
                                     │  OpenAI function-       │
                                     │  calling loop            │
                                     └───────┬───────┬─────────┘
                                             │       │
                               ┌─────────────┘       └─────────────┐
                               ▼                                   ▼
                     ┌──────────────────┐               ┌──────────────────┐
                     │   search_docs     │               │  query_orders     │
                     │  (RAG, rag.py)    │               │ (text-to-SQL,      │
                     │                   │               │  sql_tool.py)      │
                     │  Chroma vector    │               │  SQLite (orders.db)│
                     │  store            │               │                    │
                     └──────────────────┘               └──────────────────┘
```

- **Frontend**: Next.js 14 (App Router), deployed on Vercel. A single chat
  page that streams tokens live via Server-Sent Events, and renders a badge
  for each tool the agent used, plus citations (doc + section) or the
  generated SQL underneath each answer.
- **Backend**: FastAPI, deployed on Render via the root `Dockerfile`. One
  streaming endpoint (`POST /chat`) wrapping the agent loop.
- **Agent**: a single OpenAI function-calling loop (`app/agent.py`) with two
  tools — `search_docs` and `query_orders`. The model decides which to call,
  and can call both in the same turn for questions that span both sources.
- **Vector store**: Chroma, persisted to disk.
- **Structured store**: SQLite, loaded once from `orders.csv` at container
  startup. Never embedded — the agent only ever sees the schema, and writes
  real SQL against it.

---

## Why these choices

**Chroma over Pinecone/pgvector/Supabase.** Zero external infrastructure to
provision for a ~26-chunk corpus — persists to disk, runs in-process, and is
one dependency instead of a hosted account + connection string. Would
reconsider for a larger corpus, multi-tenant setup, or if the vector store
needed to be shared across multiple backend instances (Chroma's local
persistence doesn't do that well).

**`text-embedding-3-small` + `gpt-4o-mini`.** Cheap, fast, and more than
sufficient for a 5-document corpus and a 200-row table — this isn't a task
that benefits from a larger model, and keeping latency low matters more for
a chat UI with streaming.

**OpenAI function calling for routing, not a keyword classifier.** The
assignment explicitly asks for an *agentic* system that "decides on its own"
which tool to use and "may use both." A hand-coded classifier (e.g. "if the
question contains a dollar amount or 'revenue', use SQL") would satisfy the
single-source cases but can't cleanly handle a mixed question like *"our
policy allows 30-day returns — does order ORD-1002 still qualify?"* without
a growing pile of special-case rules. Giving the model both tools and a
clear description of each lets it decide naturally, and lets it chain tool
calls (fetch the order's date via SQL, then reason against the retrieved
policy chunk) without any hardcoded "if mixed then do both" logic.

**Section-aware document chunking over fixed-size windows.** These are short
policy documents where a whole section (e.g. "3. Refund Processing") is the
natural unit of a citable fact. A fixed-size sliding window would sometimes
split a policy rule across two chunks and produce a citation that doesn't
actually contain the full rule. The chunker detects both numbered headers
("1. Return Window") and short Title-Case headers with no numbering (the
FAQ doc uses "Order Tracking" style headers) and falls back to a sliding
window only if a section is unusually long.

**Schema-only SQL generation.** The model that writes SQL never sees the
actual row data — only column names and types. This keeps the prompt small,
and more importantly makes the column-hallucination guard meaningful: if the
model has never seen a `refund_reason` column, it has no way to reference
one, and if it tries, the guard rejects the query before it runs.

**Relevance-threshold fallback in RAG.** Rather than always answering from
whatever chunks come back top-4, the system compares the best match's cosine
distance against a fixed threshold. If nothing is close enough, it returns
the fallback instead of forcing an answer from irrelevant context — this is
what keeps out-of-scope questions ("what's the capital of France?") from
getting a confidently wrong answer stitched together from unrelated policy
text.

---

## How routing works

1. The user's question goes to the agent with a system prompt describing
   both tools:
   - `search_docs(query)` — searches the 5 policy/FAQ PDFs
   - `query_orders(question)` — translates a **plain data-fetch** question
     into SQL and runs it
2. The model (via OpenAI's function-calling) decides whether to call zero,
   one, or both tools, and can call them in sequence — e.g. for a mixed
   question, it typically calls `query_orders` first to get a factual date
   or status, then `search_docs` to retrieve the relevant policy chunk, then
   reasons over both in its final answer.
3. A key design detail: **`query_orders` is instructed to only accept plain
   factual lookups** (e.g. "what is the order_date and status for
   ORD-1002"), not eligibility judgments (e.g. "did ORD-1002 qualify for a
   return"). Policy reasoning stays with the top-level agent, which has
   access to both tool results. This was a real bug I hit during testing —
   see below.
4. If neither tool returns relevant information, the agent responds with a
   fixed fallback string rather than answering from general knowledge.
5. Streaming: every round is streamed from the OpenAI API. A round where the
   model is building a tool call is buffered silently (tool-call arguments
   aren't valid JSON until fully assembled anyway); a round with no tool
   calls is the final answer, and its tokens are forwarded to the client
   live as they arrive.

---

## Testing / debugging highlights

Three real bugs were found and fixed by actually running the system against
the provided dataset, rather than just eyeballing the code:

1. **Chunking regex only matched numbered headers.** The initial chunker
   split sections on patterns like `"1. Return Window"`, which worked for
   4 of the 5 PDFs but collapsed the FAQ doc (which uses unnumbered
   Title-Case headers like "Order Tracking") into 2 oversized chunks
   instead of 5 well-scoped ones. Fixed by generalizing header detection to
   catch both styles.

2. **The column-hallucination guard flagged valid string literals as
   unknown columns.** The SQL validator's regex-based "did the model invent
   a column?" check ran against the raw SQL string, so `WHERE status =
   'pending'` got the literal text `pending` flagged as an unrecognized
   identifier — the check didn't know the difference between a column name
   and text inside quotes. This silently rejected two otherwise-correct
   queries (`status = 'pending'`, `status = 'delivered'`) and forced them
   into the fallback. Fixed by stripping quoted string literals from the
   SQL before running the identifier check.

3. **`query_orders` was sometimes asked eligibility questions it can't
   answer.** In an early version of the mixed-question flow, the agent
   would pass something like *"did order ORD-1002 qualify for a return"*
   directly to `query_orders`. Since that's a judgment call, not a SQL-
   expressible fact, the SQL-generation prompt correctly returned
   `NOT_APPLICABLE` — but this meant the mixed-question path silently lost
   the actual order data and the agent had to guess. Fixed by explicitly
   instructing the top-level agent to only send `query_orders` plain
   factual lookups (dates, statuses, amounts) and keep policy judgment for
   itself.

There's also a small independent verification script
(`scripts/verify_ground_truth.py`) that computes expected answers to four
data questions directly from `orders.csv` with pandas — deliberately *not*
using the agent's own SQL generation — and asserts the agent's answers
match. This catches cases where generated SQL runs without error but
computes the wrong thing, which a "did it crash?" check wouldn't catch.

---

## Project structure

```
app/
  agent.py       — the router/agent (function-calling loop + streaming variant)
  rag.py         — RAG retrieval + answer generation
  sql_tool.py    — text-to-SQL generation, validation, execution
  main.py        — FastAPI app, SSE /chat endpoint
ingest/
  ingest_docs.py — PDF chunking + Chroma ingestion
  load_orders.py — CSV -> SQLite loader
scripts/
  test_rag.py             — standalone RAG test
  test_sql.py              — standalone text-to-SQL test
  test_agent.py            — standalone agent/routing test (all 4 question types)
  verify_ground_truth.py   — independent pandas-computed correctness check
frontend/
  app/, components/        — Next.js chat UI
data/
  docs/          — the 5 provided policy/FAQ PDFs
  orders.csv     — the provided orders table
Dockerfile, docker-entrypoint.sh  — backend image
frontend/Dockerfile               — frontend image
docker-compose.yml                — run both together locally
```

---

## Running locally

**Backend:**
```bash
pip install -r requirements.txt
cp .env.example .env   # add your OPENAI_API_KEY
python ingest/load_orders.py
python ingest/ingest_docs.py
uvicorn app.main:app --reload --port 8000
```

**Frontend** (separate terminal):
```bash
cd frontend
npm install
cp .env.local.example .env.local
npm run dev
```
Open `http://localhost:3000`.

**Or with Docker:**
```bash
docker compose up --build
```

**Standalone verification scripts** (each proves one piece works before
wiring the next layer on top):
```bash
python scripts/test_rag.py
python scripts/test_sql.py
python scripts/test_agent.py
python scripts/verify_ground_truth.py
```

---

## Known limitations

- **Cold starts on the free-tier backend host (Render).** The backend
  spins down after ~15 minutes of inactivity; the first request after that
  takes ~30–50 seconds to wake up. Subsequent requests are fast. A paid
  tier or a keep-alive ping would remove this in a real deployment.
- **No multi-turn conversation memory.** Each question is currently sent
  to the agent independently — the frontend doesn't yet pass prior
  messages as history, even though `agent.answer()` / `agent.stream_answer()`
  accept a `history` parameter for this. Follow-up questions like "what
  about order 1235?" after asking about 1234 won't have context from the
  previous turn.
- **The column-hallucination guard is a regex heuristic, not a real SQL
  parser.** It correctly handles this schema's complexity (6 columns, no
  joins, no subqueries) but would need a proper parser (e.g. `sqlglot`) to
  stay reliable against a larger or more complex schema.
- **CORS is a single configurable origin, not a list.** Fine for one
  frontend deployment; a real multi-environment setup (staging + prod
  frontends) would need `FRONTEND_ORIGIN` to accept multiple values.
- **Vector store rebuilds from scratch on every container start.** Chroma
  ingestion runs in `docker-entrypoint.sh` at startup rather than being
  baked into the image or persisted externally, so every deploy re-embeds
  all 26 chunks. Fine at this scale (a few seconds), would need a persisted
  volume or external vector DB at larger scale.
- **Relevance threshold is a fixed constant**, not tuned against a labeled
  eval set — it was set by testing against the known out-of-scope questions
  in the assignment brief, not a systematic sweep.
