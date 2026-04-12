"""
Eval harness for the AI Support Ticket Triage System.

Run with: python evals.py

Each eval result is logged as a Logfire span so you can query accuracy trends
over time directly in the Logfire SQL explorer.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass

from dotenv import load_dotenv

load_dotenv(".env.local")

import logfire

# Configure Logfire before importing agent so the pydantic-ai integration
# captures LLM traces even in standalone eval runs.
logfire.configure()

from agent import triage_ticket  # noqa: E402
from models import Severity, SupportTicket

# ---------------------------------------------------------------------------
# Golden dataset — 10 tickets with known correct labels
# ---------------------------------------------------------------------------

@dataclass
class EvalCase:
    ticket: SupportTicket
    expected_category: str
    expected_severity: Severity


GOLDEN_DATASET: list[EvalCase] = [
    EvalCase(
        ticket=SupportTicket(
            id="eval_001",
            username="sarah.kim",
            company="Pinnacle Ventures",
            subject="Cannot access my account after password reset",
            body="I reset my password an hour ago and still cannot log in. The reset email link worked but now the new password is rejected. I've tried 5 times.",
            customer_tier="pro",
        ),
        expected_category="account_access",
        expected_severity=Severity.high,
    ),
    EvalCase(
        ticket=SupportTicket(
            id="eval_002",
            username="james.whitfield",
            company="Whitfield & Co.",
            subject="Charged twice for this month",
            body="My credit card statement shows two charges of $99 from your company on the 1st. I only have one account. Please refund the duplicate charge.",
            customer_tier="pro",
        ),
        expected_category="billing",
        expected_severity=Severity.medium,
    ),
    EvalCase(
        ticket=SupportTicket(
            id="eval_003",
            username="platform-oncall",
            company="Ironclad Systems",
            subject="Production API completely down",
            body="Your API has been returning 503 for the past 30 minutes. All of our customers are affected. This is a complete outage. We need immediate response.",
            customer_tier="enterprise",
        ),
        expected_category="bug",
        expected_severity=Severity.critical,
    ),
    EvalCase(
        ticket=SupportTicket(
            id="eval_004",
            username="nina.fowler",
            company="Freelance",
            subject="Would be great to have keyboard shortcuts",
            body="I use your app all day and would love keyboard shortcuts for common actions like creating a new record, saving, etc. Not urgent just a suggestion!",
            customer_tier="free",
        ),
        expected_category="feature_request",
        expected_severity=Severity.low,
    ),
    EvalCase(
        ticket=SupportTicket(
            id="eval_005",
            username="felix.okafor",
            company="Okafor Analytics",
            subject="Reports take 3 minutes to generate",
            body="Generating any report in the analytics section takes between 2–4 minutes. Last month it was nearly instant. Our team runs these constantly throughout the day and the slowdown is really impacting productivity.",
            customer_tier="pro",
        ),
        expected_category="performance",
        expected_severity=Severity.medium,
    ),
    EvalCase(
        ticket=SupportTicket(
            id="eval_006",
            username="security@vertexcore.io",
            company="VertexCore Technologies",
            subject="Possible data breach — unauthorized API access",
            body="Our security team detected API calls using our key from an IP address we don't own. We have rotated the key but need to know what data was accessed in the past 72 hours. This may require notifying our customers.",
            customer_tier="enterprise",
        ),
        expected_category="account_access",
        expected_severity=Severity.critical,
    ),
    EvalCase(
        ticket=SupportTicket(
            id="eval_007",
            username="paula.grant",
            company="Freelance",
            subject="Export button does nothing",
            body="When I click the 'Export to Excel' button in the data table view, nothing happens. No download, no error message, just nothing. Tried in Chrome and Edge. Other export formats (CSV, PDF) work fine.",
            customer_tier="free",
        ),
        expected_category="bug",
        expected_severity=Severity.medium,
    ),
    EvalCase(
        ticket=SupportTicket(
            id="eval_008",
            username="henry.ashford",
            company="Ashford Group",
            subject="What's included in the Enterprise plan?",
            body="Hi, I'm evaluating your Enterprise plan for our team of 150. Can you tell me what's included — specifically around SSO, audit logs, SLA guarantees, and dedicated support? Thanks.",
            customer_tier="free",
        ),
        expected_category="billing",
        expected_severity=Severity.low,
    ),
    EvalCase(
        ticket=SupportTicket(
            id="eval_009",
            username="diana.reyes",
            company="Reyes Digital",
            subject="App freezes when scrolling large datasets",
            body="The application completely freezes for 5–10 seconds when I scroll through tables with more than 1000 rows. My browser (Chrome) shows the tab as unresponsive during this time. It's been happening since last week's update.",
            customer_tier="pro",
        ),
        expected_category="performance",
        expected_severity=Severity.high,
    ),
    EvalCase(
        ticket=SupportTicket(
            id="eval_010",
            username="ben.crawford",
            company="Crawford Manufacturing",
            subject="Need to transfer account ownership",
            body="Our original account admin left the company. I need to transfer ownership to myself so I can manage billing and users. I have manager-level access but not owner access. What's the process?",
            customer_tier="pro",
        ),
        expected_category="account_access",
        expected_severity=Severity.medium,
    ),
]


# ---------------------------------------------------------------------------
# Eval runner
# ---------------------------------------------------------------------------

async def run_evals() -> None:
    print("\n" + "=" * 60)
    print("  AI Support Ticket Triage — Eval Run")
    print("=" * 60)

    results: list[dict] = []

    for case in GOLDEN_DATASET:
        print(f"\nEvaluating {case.ticket.id}: {case.ticket.subject[:50]}...")

        actual = await triage_ticket(case.ticket)

        category_correct = actual.category == case.expected_category
        severity_correct = actual.severity == case.expected_severity

        result = {
            "ticket_id": case.ticket.id,
            "expected_category": case.expected_category,
            "actual_category": actual.category,
            "expected_severity": case.expected_severity.value,
            "actual_severity": actual.severity.value,
            "category_correct": category_correct,
            "severity_correct": severity_correct,
            "confidence": actual.confidence,
        }
        results.append(result)

        # Log each eval result as a Logfire span — these become queryable data
        # points for accuracy dashboards and regression tracking over time.
        logfire.info(
            "eval.result",
            ticket_id=case.ticket.id,
            expected_category=case.expected_category,
            actual_category=actual.category,
            expected_severity=case.expected_severity.value,
            actual_severity=actual.severity.value,
            category_correct=category_correct,
            severity_correct=severity_correct,
            confidence=actual.confidence,
        )

        status = "[PASS]" if (category_correct and severity_correct) else "[FAIL]"
        print(f"  {status} category={actual.category!r} (expected {case.expected_category!r}), "
              f"severity={actual.severity.value!r} (expected {case.expected_severity.value!r}), "
              f"confidence={actual.confidence:.0%}")

    # ---------------------------------------------------------------------------
    # Summary table
    # ---------------------------------------------------------------------------
    total = len(results)
    cat_correct = sum(1 for r in results if r["category_correct"])
    sev_correct = sum(1 for r in results if r["severity_correct"])
    both_correct = sum(1 for r in results if r["category_correct"] and r["severity_correct"])
    avg_confidence = sum(r["confidence"] for r in results) / total

    print("\n" + "=" * 60)
    print("  Summary")
    print("=" * 60)
    print(f"  Total tickets evaluated : {total}")
    print(f"  Overall accuracy        : {both_correct}/{total} ({both_correct/total:.0%})")
    print(f"  Category accuracy       : {cat_correct}/{total} ({cat_correct/total:.0%})")
    print(f"  Severity accuracy       : {sev_correct}/{total} ({sev_correct/total:.0%})")
    print(f"  Avg confidence          : {avg_confidence:.0%}")

    # Per-category accuracy
    categories = sorted({r["expected_category"] for r in results})
    if len(categories) > 1:
        print("\n  Per-category accuracy:")
        for cat in categories:
            cat_results = [r for r in results if r["expected_category"] == cat]
            cat_pass = sum(1 for r in cat_results if r["category_correct"])
            print(f"    {cat:<20} {cat_pass}/{len(cat_results)}")

    print("=" * 60 + "\n")

    # Log aggregate eval metrics as a summary span for trend queries.
    logfire.info(
        "eval.summary",
        total=total,
        overall_accuracy=both_correct / total,
        category_accuracy=cat_correct / total,
        severity_accuracy=sev_correct / total,
        avg_confidence=avg_confidence,
    )


if __name__ == "__main__":
    asyncio.run(run_evals())
