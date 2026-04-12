from __future__ import annotations

from dotenv import load_dotenv

load_dotenv(".env.local")

import logfire
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

# Configure Logfire first — this enables automatic instrumentation for
# pydantic-ai (LLM calls, token counts, structured outputs) and FastAPI
# (request traces, route spans, validation errors).
logfire.configure()
logfire.instrument_pydantic_ai()  # sets gen_ai.agent.name so agents appear in the Logfire Agents view
logfire.instrument_asyncpg()  # captures every asyncpg query as a span with SQL, parameters, and row counts

from agent import triage_ticket  # noqa: E402 — must import after logfire.configure()
from database import close_db, get_all_results, init_db, save_triage_result
from models import SupportTicket, TriageResponse
from seed_data import SEED_TICKETS

app = FastAPI(title="AI Support Ticket Triage System")


@app.on_event("startup")
async def startup() -> None:
    await init_db()


@app.on_event("shutdown")
async def shutdown() -> None:
    await close_db()

# Instrument FastAPI — captures every request as a trace with route, method,
# status code, and latency. Unhandled exceptions are logged automatically.
logfire.instrument_fastapi(app)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# Mount static files for the frontend
app.mount("/static", StaticFiles(directory="static"), name="static")

# In-memory ticket store — seed data only, triage results are persisted to PostgreSQL
_ticket_store: dict[str, SupportTicket] = {t.id: t for t in SEED_TICKETS}


@app.get("/", include_in_schema=False)
async def serve_index() -> FileResponse:
    return FileResponse("static/index.html")


@app.get("/tickets", response_model=list[SupportTicket])
async def list_tickets() -> list[SupportTicket]:
    """Return all seed tickets."""
    return list(_ticket_store.values())


@app.post("/triage", response_model=TriageResponse)
async def triage_single(ticket: SupportTicket) -> TriageResponse:
    """Triage a single ticket and return structured results."""
    result = await triage_ticket(ticket)

    # Record triage outcome attributes on the FastAPI request span so every
    # trace in Logfire carries category, severity, and confidence for SQL queries.
    logfire.info(
        "triage.complete",
        ticket_id=ticket.id,
        customer_tier=ticket.customer_tier,
        category=result.category,
        severity=result.severity.value,
        confidence=result.confidence,
    )

    await save_triage_result(ticket.model_dump(), result.model_dump())
    return TriageResponse(ticket=ticket, result=result)


class BatchRequest(BaseModel):
    ticket_ids: list[str]


@app.post("/triage/batch", response_model=list[TriageResponse])
async def triage_batch(body: BatchRequest) -> list[TriageResponse]:
    """Triage multiple tickets by ID. Great for pre-populating Logfire before a demo."""
    responses: list[TriageResponse] = []

    for ticket_id in body.ticket_ids:
        ticket = _ticket_store.get(ticket_id)
        if ticket is None:
            raise HTTPException(status_code=404, detail=f"Ticket {ticket_id!r} not found")

        result = await triage_ticket(ticket)

        # Emit a span per ticket so batch runs produce rich, queryable trace data.
        logfire.info(
            "triage.batch.item",
            ticket_id=ticket.id,
            customer_tier=ticket.customer_tier,
            category=result.category,
            severity=result.severity.value,
            confidence=result.confidence,
        )

        await save_triage_result(ticket.model_dump(), result.model_dump())
        responses.append(TriageResponse(ticket=ticket, result=result))

    return responses


@app.get("/results")
async def list_results() -> list[dict]:
    """Return all stored triage results, newest first."""
    return await get_all_results()


class SendResponseRequest(BaseModel):
    ticket_id: str
    recipient: str
    draft: str


@app.post("/send-response")
async def send_response(body: SendResponseRequest) -> None:
    """Send the draft response via email. Intentionally fails with an API key error."""
    with logfire.span(
        "email.send",
        ticket_id=body.ticket_id,
        recipient=body.recipient,
        provider="sendgrid",
    ):
        # Simulate the API key check that fails
        logfire.error(
            "email.send.failed",
            ticket_id=body.ticket_id,
            recipient=body.recipient,
            provider="sendgrid",
            error_code="unauthorized",
            error_message="The provided API key does not have the required 'Mail Send' permission. "
            "Rotate the key in the SendGrid dashboard and update SENDGRID_API_KEY.",
        )
        raise HTTPException(status_code=502, detail="Failed to send email response")
