"""
Data contracts for the Full-Stack Requirement Planner Worker.

Every tool in this system reads and writes these typed objects instead of
raw dicts/strings. This is the "tool contract" layer referenced in TOOLS.md.
"""
from __future__ import annotations

from enum import Enum
from typing import List, Optional
from pydantic import BaseModel, Field


# --------------------------------------------------------------------------
# Workflow state
# --------------------------------------------------------------------------

class WorkerState(str, Enum):
    INTAKE = "INTAKE"
    CLASSIFY = "CLASSIFY"
    PLANNING = "PLANNING"
    VALIDATING = "VALIDATING"
    RETRYING = "RETRYING"
    OUTPUT = "OUTPUT"
    ESCALATED_AMBIGUOUS = "ESCALATED_AMBIGUOUS"
    ESCALATED_TOOL_FAILURE = "ESCALATED_TOOL_FAILURE"


# --------------------------------------------------------------------------
# Classification (Month-1 "decide whether to proceed" step)
# --------------------------------------------------------------------------

class CompletenessReport(BaseModel):
    completeness_score: float = Field(..., ge=0.0, le=1.0)
    missing_critical_elements: List[str] = Field(default_factory=list)
    detected_actor: Optional[str] = None
    detected_core_entity: Optional[str] = None
    contradictions: List[str] = Field(default_factory=list)
    should_escalate: bool = False
    reasoning: str = ""


# --------------------------------------------------------------------------
# Plan sections
# --------------------------------------------------------------------------

class FrontendPage(BaseModel):
    name: str
    purpose: str
    key_components: List[str] = Field(default_factory=list)
    confidence: float = Field(0.8, ge=0.0, le=1.0)


class ApiEndpoint(BaseModel):
    method: str  # GET/POST/PUT/PATCH/DELETE
    path: str
    description: str
    request_fields: List[str] = Field(default_factory=list)
    response_fields: List[str] = Field(default_factory=list)
    confidence: float = Field(0.8, ge=0.0, le=1.0)


class DbColumn(BaseModel):
    name: str
    type: str
    constraints: List[str] = Field(default_factory=list)


class DbTable(BaseModel):
    name: str
    columns: List[DbColumn]
    relations: List[str] = Field(default_factory=list)
    confidence: float = Field(0.8, ge=0.0, le=1.0)


class ValidationRule(BaseModel):
    field: str
    rule: str


class EdgeCase(BaseModel):
    scenario: str
    expected_behavior: str


class TestCase(BaseModel):
    name: str
    type: str  # unit / integration / e2e
    steps: List[str]
    expected_result: str


class Assumption(BaseModel):
    text: str
    confidence: float = Field(..., ge=0.0, le=1.0)


class RequirementPlan(BaseModel):
    """The successful, autonomous output of the worker."""
    requirement_summary: str
    frontend_pages: List[FrontendPage] = Field(default_factory=list)
    api_endpoints: List[ApiEndpoint] = Field(default_factory=list)
    db_tables: List[DbTable] = Field(default_factory=list)
    validation_rules: List[ValidationRule] = Field(default_factory=list)
    edge_cases: List[EdgeCase] = Field(default_factory=list)
    test_cases: List[TestCase] = Field(default_factory=list)
    assumptions: List[Assumption] = Field(default_factory=list)
    overall_confidence: float = Field(..., ge=0.0, le=1.0)


class EscalationReport(BaseModel):
    """What the worker produces INSTEAD of a plan when it decides to stop."""
    reason: str  # "ambiguous_requirement" | "tool_failure" | "contradiction"
    explanation: str
    missing_information_needed: List[str] = Field(default_factory=list)
    partial_plan: Optional[RequirementPlan] = None
    suggested_clarifying_questions: List[str] = Field(default_factory=list)


class RunResult(BaseModel):
    run_id: str
    final_state: WorkerState
    plan: Optional[RequirementPlan] = None
    escalation: Optional[EscalationReport] = None
    retries_used: int = 0
