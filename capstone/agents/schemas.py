from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class IntakeResult(BaseModel):
    case_id: str
    covered: bool
    coverage_reasons: list[str] = Field(default_factory=list)
    clause_ids: list[str] = Field(default_factory=list)
    duplicate_of: str | None = None
    notes: str = ""


class DocResult(BaseModel):
    doc_id: str
    doc_type: str
    filename: str | None = None
    ocr_confidence: float
    injection_flag: bool
    fields_ok: bool
    notes: str = ""


class RoutingResult(BaseModel):
    case_id: str
    adjuster_id: str
    approver_id: str
    approval_requested: bool
    reason: str


class CommsResult(BaseModel):
    case_id: str
    actions: list[str] = Field(default_factory=list)
    sla_scheduled: bool = False


class AgentRun(BaseModel):
    name: str
    output: dict[str, Any] = Field(default_factory=dict)
    tool_calls: list[dict[str, Any]] = Field(default_factory=list)
    tool_errors: int = 0
    tokens: int = 0
    error: str | None = None
