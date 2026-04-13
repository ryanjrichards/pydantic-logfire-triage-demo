# AI Support Ticket Triage System

A FastAPI + pydantic-ai demo that triages support tickets using Gemini 2.5 Flash, with full observability via Logfire and persistent storage in PostgreSQL.

**GitHub:** https://github.com/ryanjrichards/pydantic-logfire-triage-demo

## Setup

```bash
git clone https://github.com/ryanjrichards/pydantic-logfire-triage-demo.git
cd pydantic-logfire-triage-demo
pip install -r requirements.txt
```

Copy the env template and fill in your credentials:

```bash
cp .env .env.local
```

```ini
# .env.local
GOOGLE_API_KEY=...    # aistudio.google.com/apikey
LOGFIRE_TOKEN=...     # logfire.pydantic.dev → project settings → tokens
DATABASE_URL=postgresql://user:password@localhost:5432/triage
LOGFIRE_API_KEY=...   # project:read_variables scope — for managed variables
SERVICE=support-triage
ENV=dev
```

`.env.local` is gitignored — your secrets stay local. `.env` is committed as an empty template.

## Database

Triage results are persisted to PostgreSQL via asyncpg. The app creates the `triage_results` table automatically on startup — no migrations needed.

```sql
CREATE TABLE triage_results (
    id         SERIAL PRIMARY KEY,
    ticket_id  TEXT NOT NULL,
    triaged_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    ticket     JSONB NOT NULL,
    result     JSONB NOT NULL
);
```

Every `/triage` and `/triage/batch` call writes a row. Retrieve all stored results:

```
GET /results
```

## Run

```bash
source .env.local && uvicorn main:app --reload
```

Open http://localhost:8000

## Managed variables

The agent system prompt is a Logfire managed variable (`my_prompt`). Set and update its value from the Logfire UI under **Variables** — the running app reads the current value on every request without redeploying.

Requires `LOGFIRE_API_KEY` (separate from `LOGFIRE_TOKEN`) with `project:read_variables` scope. Get one from **Project Settings → Tokens → New Token**.

## Pre-populate Logfire before a demo

Run evals to generate a rich trace history (10 tickets × structured eval spans):

```bash
python evals.py
```

Then hit **Triage All** in the UI to generate 20 more traces across all categories and severity levels.

## Logfire SQL queries for the demo

Paste these into the Logfire SQL explorer:

### 1. Ticket volume by category
```sql
SELECT
  attributes->>'category' AS category,
  count(*) AS count
FROM records
WHERE message = 'triage.complete'
GROUP BY category
ORDER BY count DESC
```

### 2. P95 agent latency by customer tier (seconds)
```sql
SELECT
  attributes->>'customer_tier' AS tier,
  round((percentile_cont(0.95) WITHIN GROUP (ORDER BY duration))::numeric, 2) AS p95_seconds,
  count(*) AS calls
FROM records
WHERE span_name = 'agent.triage'
GROUP BY tier
ORDER BY p95_seconds DESC
LIMIT 20
```

### 3. Eval pass rate over time
```sql
SELECT
  date_trunc('minute', start_timestamp) AS bucket,
  avg(CASE WHEN (attributes->'assertions'->'CategoryCorrect'->>'value')::boolean THEN 1.0 ELSE 0.0 END) AS category_accuracy,
  avg(CASE WHEN (attributes->'assertions'->'SeverityCorrect'->>'value')::boolean THEN 1.0 ELSE 0.0 END) AS severity_accuracy,
  avg((attributes->'attributes'->>'confidence')::float) AS avg_confidence
FROM records
WHERE attributes->>'task_name' = 'eval_task'
GROUP BY bucket
ORDER BY bucket
LIMIT 500
```

### 4. Triage results
```sql
SELECT
  start_timestamp AS triaged_at,
  attributes->>'ticket_id' AS ticket_id,
  attributes->>'customer_tier' AS tier,
  attributes->>'category' AS category,
  attributes->>'severity' AS severity,
  round((attributes->>'confidence')::numeric, 2) AS confidence
FROM records
WHERE message = 'triage.complete'
ORDER BY start_timestamp DESC
LIMIT 50
```

## Step-by-step demo script

1. **Open the UI** — go to http://localhost:8000. The ticket queue loads 20 realistic tickets.

2. **Triage a ticket live** — click any ticket card, hit "Triage →". Watch the result panel animate in: category badge, severity color, confidence bar, draft response. The result is saved to PostgreSQL automatically.

3. **Triage a feature request (roadmap error demo)** — click the **"Feature request: bulk export to CSV"** ticket (jen.kowalski) and triage it. The AI agent categorizes it as `feature_request` and a nested `roadmap.link` span fires to auto-link it to the Linear product backlog. The OAuth token is expired, so the span fails with `error_code: oauth_token_expired`. In Logfire you'll see the full trace: the FastAPI request → `agent.triage` → `roadmap.link` → `roadmap.link.failed` error log with the actionable error message. The failed span surfaces in the Issues view, grouped by fingerprint across all feature-request tickets. Any other ticket categorized as `feature_request` triggers the same error — useful for showing how a single misconfigured integration can affect multiple traces.

4. **Send a response (error demo)** — with any result on screen, click **Send Response**. The request hits `/send-response`, which simulates a misconfigured SendGrid API key and returns a 502. You'll see "Failed to send response." in the UI and a `logfire.error` span in Logfire with the full error context (`error_code`, `provider`, `ticket_id`). Good hook for showing how Logfire surfaces application errors alongside traces.

5. **Pivot to Logfire** — open your Logfire project. You'll see a trace for the HTTP request, nested inside it the `agent.triage` span (set via `logfire.instrument_pydantic_ai()`), and inside *that* the full pydantic-ai LLM call with token counts, prompt, and structured output. The agent appears by name (`support-triage`) in the Logfire Agents view.

6. **Run SQL queries** — paste the queries above into the Logfire SQL explorer. Show ticket volume by category, P95 latency by customer tier, and eval accuracy trends. Query the PostgreSQL table directly for the persisted history.

7. **Run evals** — in a separate terminal run `python evals.py`. Each of the 10 golden-dataset tickets is triaged and logged as a structured `eval.result` span with per-case metrics: `input_tokens`, `output_tokens`, `cost_usd`, and `confidence`. The terminal prints a summary table; the eval pass rate SQL query in Logfire shows the trend over time, and you can filter by confidence to find cases where the model was uncertain.

8. **Hit "Triage All"** — back in the UI, click the green "Triage All" button to batch-triage all 20 seed tickets in one shot. The history feed (collapsible via the header) fills up, Logfire captures every trace, and all results land in PostgreSQL.
