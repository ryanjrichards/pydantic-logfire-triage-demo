from __future__ import annotations

from enum import Enum
from typing import Literal

from pydantic import BaseModel, Field


class SupportTicket(BaseModel):
    id: str
    subject: str
    body: str
    customer_tier: Literal["free", "pro", "enterprise"]


class Severity(str, Enum):
    low = "low"
    medium = "medium"
    high = "high"
    critical = "critical"


class TriageResult(BaseModel):
    category: str
    severity: Severity
    summary: str
    draft_response: str
    confidence: float = Field(ge=0.0, le=1.0)


class TriageResponse(BaseModel):
    ticket: SupportTicket
    result: TriageResult
