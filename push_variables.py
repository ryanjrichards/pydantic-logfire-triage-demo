"""Push managed variable definitions (including label values) to Logfire.

Usage:
    source .env.local && python push_variables.py

Requires LOGFIRE_TOKEN with project:write_variables scope.
"""
import json

import logfire
from logfire.variables.config import LabeledValue, LatestVersion, Rollout, VariableConfig, VariablesConfig

logfire.configure()

SIMPLIFIED_PROMPT = """You are a customer support triage assistant. Analyze each support ticket and return structured data.

Fields to populate:
- category: billing | bug | feature_request | account_access | performance | other
- severity: low | medium | high | critical
- summary: 1–2 sentences describing the issue
- draft_response: a short, professional email reply to the customer
- confidence: 0.0–1.0

Severity quick guide: critical = down/data loss/security; high = major breakage; medium = partial issue with workaround; low = minor or cosmetic.
"""

v1_serialized = json.dumps(SIMPLIFIED_PROMPT)

config = VariablesConfig(
    variables={
        "my_prompt": VariableConfig(
            name="my_prompt",
            description="System prompt for the support-triage agent",
            labels={
                "v1": LabeledValue(version=1, serialized_value=v1_serialized),
            },
            rollout=Rollout(labels={"v1": 1.0}),
            overrides=[],
            latest_version=LatestVersion(version=1, serialized_value=v1_serialized),
            json_schema={"type": "string"},
            example=v1_serialized,
        )
    }
)

if __name__ == "__main__":
    logfire.variables_push_config(config, yes=True)
