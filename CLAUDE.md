# Architecture Reference

## Overview

FastAPI + pydantic-ai demo that triages support tickets using Gemini 2.5 Flash. Full observability via Logfire. Triage results persisted to PostgreSQL.

## Stack

| Layer | Technology |
|---|---|
| Web framework | FastAPI (async) |
| AI agent | pydantic-ai `Agent` → Gemini 2.5 Flash (`google-gla:gemini-2.5-flash`) |
| Database | PostgreSQL via asyncpg connection pool |
| Observability | Logfire — auto-instruments FastAPI, asyncpg, and pydantic-ai |
| Evals | pydantic-evals (via `logfire[datasets]`) — `Dataset` + `Case` + evaluators |
| Frontend | Vanilla JS single-page app served from `static/index.html` |

## File Map

```
main.py          — FastAPI app, all routes, Logfire configuration
agent.py         — pydantic-ai Agent definition and triage_ticket() function
models.py        — Pydantic models: SupportTicket, TriageResult, TriageResponse, Severity
database.py      — asyncpg pool, init_db / save_triage_result / get_all_results
seed_data.py     — 20 hardcoded SupportTicket fixtures loaded into memory on startup
evals.py         — pydantic-evals Dataset with 10 golden cases; evaluators check category + severity
static/index.html — Frontend: ticket queue, result panel, history feed (all vanilla JS)
requirements.txt — Python dependencies
.env             — Committed template (empty values)
.env.local       — Local secrets (gitignored)
```

## Key Patterns

### Startup order matters
`logfire.configure()` and `logfire.instrument_asyncpg()` must be called before importing `agent.py` and before the asyncpg pool is created. The import order in `main.py` enforces this.

### Ticket store vs database
Tickets (`SupportTicket`) live in a plain dict `_ticket_store` in memory — they are seed data only and never written to the DB. Triage *results* are written to PostgreSQL after every successful triage.

### Logfire instrumentation points
- `logfire.instrument_fastapi(app)` — every HTTP request as a trace
- `logfire.instrument_asyncpg()` — every SQL query as a child span
- `logfire.instrument_pydantic_ai()` — sets `gen_ai.agent.name` so agents appear in the Logfire Agents view; must be called explicitly
- `logfire.span("agent.triage", ...)` in `agent.py` — wraps each agent run
- `logfire.info("triage.complete", ...)` in `main.py` — emits queryable attributes per triage
- `logfire.error("email.send.failed", ...)` in `/send-response` — intentional error demo

### Agent name
The pydantic-ai `Agent` is created with `name="support-triage"`. This sets the `gen_ai.agent.name` OTel attribute, which Logfire uses to surface the agent in the Agents view.

## API Routes

| Method | Path | Description |
|---|---|---|
| `GET` | `/` | Serves `static/index.html` |
| `GET` | `/tickets` | Returns all 20 seed tickets |
| `POST` | `/triage` | Triages a single ticket; saves result to DB |
| `POST` | `/triage/batch` | Triages multiple tickets by ID |
| `GET` | `/results` | Returns all saved triage results (newest first) |
| `POST` | `/send-response` | Intentionally fails with a simulated SendGrid API key error for demo purposes |

## Database Schema

```sql
CREATE TABLE triage_results (
    id          SERIAL PRIMARY KEY,
    ticket_id   TEXT NOT NULL,
    triaged_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
    ticket      JSONB NOT NULL,   -- full SupportTicket snapshot
    result      JSONB NOT NULL    -- full TriageResult snapshot
);
```

Table is created automatically on startup via `init_db()`. No migrations.

## Data Models

```python
SupportTicket   id, subject, body, customer_tier, username, company
TriageResult    category, severity, summary, draft_response, confidence
TriageResponse  ticket: SupportTicket, result: TriageResult
Severity        low | medium | high | critical  (str enum)
```

`category` is a free-form string from the LLM: `billing`, `bug`, `feature_request`, `account_access`, `performance`, `other`.

## Environment Variables

```ini
GOOGLE_API_KEY=    # Google AI Studio key for Gemini
LOGFIRE_TOKEN=     # Logfire project token
DATABASE_URL=      # asyncpg DSN, e.g. postgresql://user:password@localhost:5432/triage
```

## Frontend Behaviour

- On load: fetches `/tickets` and `/results` in parallel. History feed pre-populated from DB; ticket cards show "✓ triaged" pill for previously triaged tickets.
- Clicking a triaged ticket: shows previous result directly (skips preview).
- Clicking an untriaged ticket: shows ticket preview with "Triage this ticket" button.
- Re-triage button: appears on result view for previously triaged tickets.
- Send Response button: POSTs to `/send-response`, always fails, shows "Failed to send response." error banner.
- History feed: collapsed by default, click header to expand/collapse.
- Triage All: batch-triages all 20 seed tickets via `/triage/batch`.

## Running Locally

```bash
# Start Postgres
docker run -d --name triage-db \
  -e POSTGRES_USER=user -e POSTGRES_PASSWORD=password -e POSTGRES_DB=triage \
  -p 5432:5432 postgres:16

# Start app
source .env.local && uvicorn main:app --reload
```

## Pre-populating Logfire

```bash
python evals.py          # 10 golden tickets → structured eval.result spans
# then hit Triage All in the UI for 20 more traces
```
