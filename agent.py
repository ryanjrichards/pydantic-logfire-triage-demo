from __future__ import annotations

import logfire
from pydantic_ai import Agent

from models import SupportTicket, TriageResult

# pydantic-ai automatically integrates with Logfire when logfire is configured —
# every agent.run() call produces a full trace with LLM tokens, prompts, and
# structured outputs, with zero extra instrumentation code needed.
agent = Agent(
    "google-gla:gemini-2.0-flash",
    result_type=TriageResult,
    system_prompt="""You are an expert customer support triage assistant.

Your job is to analyze incoming support tickets and produce structured triage data.

For each ticket, you must determine:
- category: one of billing, bug, feature_request, account_access, performance, other
- severity: one of low, medium, high, critical
- summary: a concise 1–2 sentence summary of the issue
- draft_response: a professional, empathetic first-response email to send to the customer
- confidence: a float from 0.0 to 1.0 representing how confident you are in your triage

Severity guidelines:
- critical: service is completely down, data loss, security breach, or enterprise customer blocked
- high: major functionality broken, significant business impact, or pro/enterprise customer severely impacted
- medium: partial functionality issue, workaround exists, or moderate customer impact
- low: minor inconvenience, cosmetic issue, general question, or easily worked around

Draft response guidelines:
- Address the customer by acknowledging their issue
- Be empathetic and professional
- Provide any immediate workarounds if applicable
- Set clear expectations for next steps
- Keep it concise but warm
""",
)


async def triage_ticket(ticket: SupportTicket) -> TriageResult:
    # Wrap the agent call in a named span so Logfire captures ticket-level
    # attributes alongside the automatic pydantic-ai LLM trace.
    with logfire.span(
        "agent.triage",
        ticket_id=ticket.id,
        customer_tier=ticket.customer_tier,
    ):
        prompt = f"""Please triage this support ticket:

Subject: {ticket.subject}
Customer Tier: {ticket.customer_tier}

Body:
{ticket.body}
"""
        result = await agent.run(prompt)
        return result.data
