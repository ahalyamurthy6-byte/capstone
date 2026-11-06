from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

CaseStatus = Literal[
    "NEW",
    "REGISTERED",
    "DOCS_PROCESSED",
    "DOCS_VALIDATED",
    "SUMMARISED",
    "ROUTED",
    "AWAITING_DOCUMENTS",
    "AWAITING_APPROVAL",
    "MANUAL_REVIEW",
    "APPROVED",
    "REJECTED",
    "MORE_INFO",
]


class Case(BaseModel):
    model_config = ConfigDict(extra="ignore")

    case_id: str
    policy_number: str | None = None
    claimant_name: str | None = None
    claimant_email: str | None = None
    incident_date: date | None = None
    claim_type: str | None = None
    amount: Decimal | None = None
    description: str | None = None
    status: CaseStatus = "NEW"
    duplicate_of: str | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None


class Policy(BaseModel):
    model_config = ConfigDict(extra="ignore")

    policy_number: str
    customer_id: str | None = None
    product: str | None = None
    start_date: date | None = None
    end_date: date | None = None
    sum_insured: Decimal | None = None
    exclusions: list[str] = Field(default_factory=list)


class CoverageResult(BaseModel):
    covered: bool
    reasons: list[str] = Field(default_factory=list)
    clause_ids: list[str] = Field(default_factory=list)


class DocumentInfo(BaseModel):
    model_config = ConfigDict(extra="ignore")

    doc_id: str
    case_id: str | None = None
    file_path: str | None = None
    doc_type: str | None = None
    ocr_text: str | None = None
    ocr_confidence: float | None = None
    injection_flag: bool = False
    fields: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime | None = None


class OcrResult(BaseModel):
    text: str
    ocr_confidence: float
    injection_flag: bool
    injection_snippets: list[str] = Field(default_factory=list)


class Classification(BaseModel):
    doc_type: Literal["invoice", "medical_report", "claim_form", "police_report", "photo", "other"]
    confidence: float


class ExtractedFields(BaseModel):
    claimant_name: str | None = None
    policy_number: str | None = None
    incident_date: date | None = None
    amount: Decimal | None = None
    provider: str | None = None
    invoice_number: str | None = None
    confidence: float = 0.0


class ValidationResult(BaseModel):
    ok: bool
    missing_types: list[str] = Field(default_factory=list)
    mismatches: list[str] = Field(default_factory=list)
    low_confidence_docs: list[str] = Field(default_factory=list)
    injection_docs: list[str] = Field(default_factory=list)


class Risk(BaseModel):
    text: str
    clause_id: str | None = None


class CaseSummary(BaseModel):
    facts: list[str] = Field(default_factory=list)
    evidence: list[str] = Field(default_factory=list)
    missing_info: list[str] = Field(default_factory=list)
    risks: list[Risk] = Field(default_factory=list)
    next_action: str


class SimilarCase(BaseModel):
    case_id: str
    score: float
    reason: str


class WordingHit(BaseModel):
    clause_id: str
    title: str
    text: str
    score: float


class StaffLoad(BaseModel):
    staff_id: str
    name: str
    role: str
    approval_limit: Decimal | float
    open_cases: int


class Ack(BaseModel):
    ok: bool
    message: str


class ToolError(BaseModel):
    error: str
    hint: str | None = None
