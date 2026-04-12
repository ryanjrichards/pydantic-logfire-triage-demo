"""
Eval harness for the AI Support Ticket Triage System.

Run with: python evals.py

Uses pydantic-evals (via logfire[datasets]) to run each golden-dataset case
through the agent and evaluate category and severity accuracy. Results are
automatically logged to Logfire as structured spans.
"""

from __future__ import annotations

import asyncio
import sys
from contextlib import nullcontext
from dataclasses import dataclass

from dotenv import load_dotenv


load_dotenv(".env.local")

import logfire

# Configure Logfire before importing agent so the pydantic-ai integration
# captures LLM traces even in standalone eval runs.
logfire.configure()
logfire.instrument_pydantic_ai()

import genai_prices
from pydantic_evals import Case, Dataset, increment_eval_metric, set_eval_attribute
from pydantic_evals.evaluators import Evaluator, EvaluatorContext

from agent import agent, run_triage  # noqa: E402
from models import Severity, SupportTicket, TriageResult


# ---------------------------------------------------------------------------
# Metadata — expected labels per case
# ---------------------------------------------------------------------------

@dataclass
class EvalMetadata:
    expected_category: str
    expected_severity: Severity


# ---------------------------------------------------------------------------
# Evaluators — dataclass subclasses of Evaluator as required by pydantic-evals
# ---------------------------------------------------------------------------

@dataclass
class CategoryCorrect(Evaluator[SupportTicket, TriageResult, EvalMetadata]):
    def evaluate(self, ctx: EvaluatorContext[SupportTicket, TriageResult, EvalMetadata]) -> bool:
        return ctx.output.category == ctx.metadata.expected_category


@dataclass
class SeverityCorrect(Evaluator[SupportTicket, TriageResult, EvalMetadata]):
    def evaluate(self, ctx: EvaluatorContext[SupportTicket, TriageResult, EvalMetadata]) -> bool:
        return ctx.output.severity == ctx.metadata.expected_severity


# ---------------------------------------------------------------------------
# Golden dataset — 10 tickets with known correct labels
# ---------------------------------------------------------------------------

dataset: Dataset[SupportTicket, TriageResult, EvalMetadata] = Dataset(
    name="triage-evals",
    evaluators=[CategoryCorrect(), SeverityCorrect()],
    cases=[
        Case(
            name="eval_001",
            inputs=SupportTicket(
                id="eval_001",
                username="sarah.kim",
                company="Pinnacle Ventures",
                subject="Cannot access my account after password reset",
                body="I reset my password an hour ago and still cannot log in. The reset email link worked but now the new password is rejected. I've tried 5 times.",
                customer_tier="pro",
            ),
            metadata=EvalMetadata(expected_category="account_access", expected_severity=Severity.high),
        ),
        Case(
            name="eval_002",
            inputs=SupportTicket(
                id="eval_002",
                username="james.whitfield",
                company="Whitfield & Co.",
                subject="Charged twice for this month",
                body="My credit card statement shows two charges of $99 from your company on the 1st. I only have one account. Please refund the duplicate charge.",
                customer_tier="pro",
            ),
            metadata=EvalMetadata(expected_category="billing", expected_severity=Severity.medium),
        ),
        Case(
            name="eval_003",
            inputs=SupportTicket(
                id="eval_003",
                username="platform-oncall",
                company="Ironclad Systems",
                subject="Production API completely down",
                body="Your API has been returning 503 for the past 30 minutes. All of our customers are affected. This is a complete outage. We need immediate response.",
                customer_tier="enterprise",
            ),
            metadata=EvalMetadata(expected_category="bug", expected_severity=Severity.critical),
        ),
        Case(
            name="eval_004",
            inputs=SupportTicket(
                id="eval_004",
                username="nina.fowler",
                company="Freelance",
                subject="Would be great to have keyboard shortcuts",
                body="I use your app all day and would love keyboard shortcuts for common actions like creating a new record, saving, etc. Not urgent just a suggestion!",
                customer_tier="free",
            ),
            metadata=EvalMetadata(expected_category="feature_request", expected_severity=Severity.low),
        ),
        Case(
            name="eval_005",
            inputs=SupportTicket(
                id="eval_005",
                username="felix.okafor",
                company="Okafor Analytics",
                subject="Reports take 3 minutes to generate",
                body="Generating any report in the analytics section takes between 2–4 minutes. Last month it was nearly instant. Our team runs these constantly throughout the day and the slowdown is really impacting productivity.",
                customer_tier="pro",
            ),
            metadata=EvalMetadata(expected_category="performance", expected_severity=Severity.medium),
        ),
        Case(
            name="eval_006",
            inputs=SupportTicket(
                id="eval_006",
                username="security@vertexcore.io",
                company="VertexCore Technologies",
                subject="Possible data breach — unauthorized API access",
                body="Our security team detected API calls using our key from an IP address we don't own. We have rotated the key but need to know what data was accessed in the past 72 hours. This may require notifying our customers.",
                customer_tier="enterprise",
            ),
            metadata=EvalMetadata(expected_category="account_access", expected_severity=Severity.critical),
        ),
        Case(
            name="eval_007",
            inputs=SupportTicket(
                id="eval_007",
                username="paula.grant",
                company="Freelance",
                subject="Export button does nothing",
                body="When I click the 'Export to Excel' button in the data table view, nothing happens. No download, no error message, just nothing. Tried in Chrome and Edge. Other export formats (CSV, PDF) work fine.",
                customer_tier="free",
            ),
            metadata=EvalMetadata(expected_category="bug", expected_severity=Severity.medium),
        ),
        Case(
            name="eval_008",
            inputs=SupportTicket(
                id="eval_008",
                username="henry.ashford",
                company="Ashford Group",
                subject="What's included in the Enterprise plan?",
                body="Hi, I'm evaluating your Enterprise plan for our team of 150. Can you tell me what's included — specifically around SSO, audit logs, SLA guarantees, and dedicated support? Thanks.",
                customer_tier="free",
            ),
            metadata=EvalMetadata(expected_category="billing", expected_severity=Severity.low),
        ),
        Case(
            name="eval_009",
            inputs=SupportTicket(
                id="eval_009",
                username="diana.reyes",
                company="Reyes Digital",
                subject="App freezes when scrolling large datasets",
                body="The application completely freezes for 5–10 seconds when I scroll through tables with more than 1000 rows. My browser (Chrome) shows the tab as unresponsive during this time. It's been happening since last week's update.",
                customer_tier="pro",
            ),
            metadata=EvalMetadata(expected_category="performance", expected_severity=Severity.high),
        ),
        Case(
            name="eval_010",
            inputs=SupportTicket(
                id="eval_010",
                username="ben.crawford",
                company="Crawford Manufacturing",
                subject="Need to transfer account ownership",
                body="Our original account admin left the company. I need to transfer ownership to myself so I can manage billing and users. I have manager-level access but not owner access. What's the process?",
                customer_tier="pro",
            ),
            metadata=EvalMetadata(expected_category="account_access", expected_severity=Severity.medium),
        ),
    ],
)


# ---------------------------------------------------------------------------
# Eval runner
# ---------------------------------------------------------------------------

async def run_evals(model: str | None = None) -> None:
    model_name = model or "google-gla:gemini-2.5-flash"

    async def eval_task(ticket: SupportTicket) -> TriageResult:
        result = await run_triage(ticket)
        usage = result.usage()

        set_eval_attribute("model", model_name)
        set_eval_attribute("confidence", result.output.confidence)
        increment_eval_metric("input_tokens", usage.input_tokens)
        increment_eval_metric("output_tokens", usage.output_tokens)

        try:
            price = genai_prices.calc_price(usage, model_name)
            increment_eval_metric("cost_usd", float(price.total_price))
        except Exception:
            pass

        return result.output

    ctx = agent.override(model=model) if model else nullcontext()
    with ctx:
        report = await dataset.evaluate(eval_task, metadata={"model": model_name})
    report.print()


if __name__ == "__main__":
    model = sys.argv[1] if len(sys.argv) > 1 else None
    asyncio.run(run_evals(model=model))
