from __future__ import annotations

import logfire
from pydantic_ai import Agent, AgentRunResult

from models import SupportTicket, TriageResult

# Managed variable — edit the value in the Logfire UI without redeploying.
# Requires LOGFIRE_API_KEY with project:read_variables scope.
my_prompt = logfire.var(
    "my_prompt",
    default="""You are an expert customer support triage assistant.

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

# pydantic-ai automatically integrates with Logfire when logfire is configured —
# every agent.run() call produces a full trace with LLM tokens, prompts, and
# structured outputs, with zero extra instrumentation code needed.
agent = Agent(
    "google-gla:gemini-2.5-flash",
    output_type=TriageResult,
    name="support-triage",
)


def _build_prompt(ticket: SupportTicket) -> str:
    return f"""Please triage this support ticket:

Subject: {ticket.subject}
Customer Tier: {ticket.customer_tier}

Body:
{ticket.body}
"""


async def run_triage(ticket: SupportTicket) -> AgentRunResult[TriageResult]:
    """Run the agent and return the full result (includes usage, messages, etc.)."""
    with my_prompt.get() as resolved:
        with agent.override(instructions=resolved.value):
            return await agent.run(_build_prompt(ticket))


async def triage_ticket(ticket: SupportTicket) -> TriageResult:
    result = await run_triage(ticket)
    return result.output
