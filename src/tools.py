"""
Tool contracts.

Each tool below has a single responsibility, a typed input, and a typed
output (see schemas.py). The orchestrator (worker.py) never calls the LLM
client directly -- it only calls these named tools, so every decision point
is independently testable and independently loggable.
"""
from __future__ import annotations

import json
from pydantic import ValidationError

from .llm_client import LLMClient, ToolFailureError
from .schemas import CompletenessReport, RequirementPlan

CLASSIFY_SYSTEM_PROMPT = """CLASSIFY_TASK
You are the classification stage of a Full-Stack Requirement Planner Worker.
Given a raw product requirement, decide if it has enough information to
safely produce a technical plan. Return ONLY JSON matching CompletenessReport.
Do not invent an actor or entity that isn't implied by the text."""

PLAN_SYSTEM_PROMPT = """PLAN_TASK
You are the planning stage of a Full-Stack Requirement Planner Worker.
Given a raw product requirement (and optionally similar past corrected
exemplars), produce a structured technical plan as JSON matching
RequirementPlan: frontend pages, backend API endpoints, DB tables,
validation rules, edge cases, and test cases. Flag any assumption you make
with an explicit confidence score. Return ONLY JSON, no prose."""

REPAIR_SYSTEM_PROMPT = """PLAN_TASK
Your previous output was not valid JSON matching the required schema.
Fix it and return ONLY valid JSON matching RequirementPlan. Do not include
any explanation, markdown fences, or extra text."""


def tool_classify_completeness(client: LLMClient, requirement: str) -> CompletenessReport:
    """Tool: classify_completeness -- decides whether to proceed or escalate."""
    raw = client.complete(CLASSIFY_SYSTEM_PROMPT, requirement)
    data = json.loads(raw)
    return CompletenessReport(**data)


def tool_generate_plan(client: LLMClient, requirement: str, exemplars: list) -> str:
    """Tool: generate_plan -- returns RAW text (may be malformed; caller validates)."""
    exemplar_context = ""
    if exemplars:
        exemplar_context = "\n\nSimilar past corrected examples:\n" + json.dumps(exemplars)
    return client.complete(PLAN_SYSTEM_PROMPT, requirement + exemplar_context)


def tool_repair_plan(client: LLMClient, requirement: str, broken_output: str) -> str:
    """Tool: repair_plan -- asks the model to fix its own malformed output."""
    prompt = f"Original requirement:\n{requirement}\n\nYour broken output:\n{broken_output}"
    return client.complete(REPAIR_SYSTEM_PROMPT, prompt)


def tool_validate_schema(raw_text: str) -> tuple[RequirementPlan | None, str | None]:
    """Tool: validate_schema -- returns (plan, None) on success or (None, error) on failure."""
    try:
        data = json.loads(raw_text)
        plan = RequirementPlan(**data)
        return plan, None
    except (json.JSONDecodeError, ValidationError) as e:
        return None, str(e)
