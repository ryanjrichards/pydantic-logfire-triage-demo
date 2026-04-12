# AI Support Ticket Triage System

A FastAPI + pydantic-ai demo that triages support tickets using Gemini 2.0 Flash, with full observability via Logfire.

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
```

`.env.local` is gitignored — your secrets stay local. `.env` is committed as an empty template.

## Run

```bash
source .env.local && uvicorn main:app --reload
```

Open http://localhost:8000

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
  percentile_cont(0.95) WITHIN GROUP (ORDER BY duration_ns / 1e9) AS p95_seconds,
  count(*) AS calls
FROM records
WHERE span_name = 'agent.triage'
GROUP BY tier
ORDER BY p95_seconds DESC
```

### 3. Eval pass rate over time
```sql
SELECT
  date_trunc('minute', start_time) AS bucket,
  avg(CASE WHEN (attributes->>'category_correct')::boolean THEN 1.0 ELSE 0.0 END) AS category_accuracy,
  avg(CASE WHEN (attributes->>'severity_correct')::boolean THEN 1.0 ELSE 0.0 END) AS severity_accuracy,
  avg((attributes->>'confidence')::float) AS avg_confidence
FROM records
WHERE message = 'eval.result'
GROUP BY bucket
ORDER BY bucket
```

## Step-by-step demo script

1. **Open the UI** — go to http://localhost:8000. The ticket queue loads 20 realistic tickets.

2. **Triage a ticket live** — click any ticket card, hit "Triage →". Watch the result panel animate in: category badge, severity color, confidence bar, draft response.

3. **Pivot to Logfire** — open your Logfire project. You'll see a trace for the HTTP request, nested inside it the `agent.triage` span, and inside *that* the full pydantic-ai LLM call with token counts, prompt, and structured output — zero extra instrumentation code needed because pydantic-ai integrates with Logfire automatically.

4. **Run SQL queries** — paste the three queries above into the Logfire SQL explorer. Show ticket volume by category, P95 latency by customer tier, and eval accuracy trends.

5. **Run evals** — in a separate terminal run `python evals.py`. Each of the 10 golden-dataset tickets is triaged and logged as a structured `eval.result` span. The terminal prints a summary table; the eval pass rate SQL query in Logfire shows the trend over time.

6. **Hit "Triage All"** — back in the UI, click the green "Triage All" button to batch-triage all 20 seed tickets in one shot. The history feed fills up and Logfire captures every trace.
