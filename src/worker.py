"""
RequirementPlannerWorker -- the orchestrator.

State machine:

    INTAKE
      |
      v
    CLASSIFY --(should_escalate=True)--> ESCALATED_AMBIGUOUS  [terminal]
      |
      v (proceed)
    PLANNING
      |
      v
    VALIDATING --(schema invalid)--> RETRYING --(max retries hit)--> ESCALATED_TOOL_FAILURE [terminal]
      |                                  |
      | (valid)                         v (repaired, re-validate)
      v                            VALIDATING
    OUTPUT [terminal]

Design principle: the worker NEVER emits a full RequirementPlan for a
requirement it classified as ambiguous. Escalation happens BEFORE planning,
not as a low-confidence plan. This is a deliberate anti-hallucination
guardrail requested in the assignment brief.
"""
from __future__ import annotations

from typing import Optional
import uuid

from .llm_client import LLMClient, ToolFailureError
from .memory import ExemplarStore
from .audit_log import AuditLogger
from .schemas import (
    WorkerState,
    RunResult,
    EscalationReport,
)
from . import tools

MAX_RETRIES = 2


class RequirementPlannerWorker:
    def __init__(
        self,
        client: LLMClient,
        memory: Optional[ExemplarStore] = None,
        logger: Optional[AuditLogger] = None,
    ):
        self.client = client
        self.memory = memory or ExemplarStore()
        self.logger = logger or AuditLogger()

    def run(self, requirement: str) -> RunResult:
        run_id = self.logger.run_id
        state = WorkerState.INTAKE
        self.logger.log("state_transition", state=state.value, requirement=requirement)

        # ---- CLASSIFY -------------------------------------------------
        state = WorkerState.CLASSIFY
        try:
            report = tools.tool_classify_completeness(self.client, requirement)
        except ToolFailureError as e:
            self.logger.log("tool_failure", tool="classify_completeness", error=str(e))
            return self._escalate_tool_failure(run_id, requirement, str(e))

        self.logger.log(
            "classification_result",
            completeness_score=report.completeness_score,
            missing=report.missing_critical_elements,
            should_escalate=report.should_escalate,
            reasoning=report.reasoning,
        )

        if report.should_escalate:
            state = WorkerState.ESCALATED_AMBIGUOUS
            escalation = EscalationReport(
                reason="ambiguous_requirement" if not report.contradictions else "contradiction",
                explanation=report.reasoning,
                missing_information_needed=report.missing_critical_elements,
                suggested_clarifying_questions=self._questions_from_missing(
                    report.missing_critical_elements
                ),
            )
            self.logger.log("escalation", reason=escalation.reason, state=state.value)
            return RunResult(run_id=run_id, final_state=state, escalation=escalation)

        # ---- PLANNING / VALIDATING / RETRYING -------------------------
        exemplars = self.memory.top_k_similar(requirement, k=2)
        state = WorkerState.PLANNING
        self.logger.log("state_transition", state=state.value, exemplars_used=len(exemplars))

        retries = 0
        raw_output: str
        try:
            raw_output = tools.tool_generate_plan(self.client, requirement, exemplars)
        except ToolFailureError as e:
            self.logger.log("tool_failure", tool="generate_plan", error=str(e))
            return self._escalate_tool_failure(run_id, requirement, str(e))

        state = WorkerState.VALIDATING
        plan, error = tools.tool_validate_schema(raw_output)

        while error is not None and retries < MAX_RETRIES:
            retries += 1
            state = WorkerState.RETRYING
            self.logger.log(
                "validation_failed_retrying",
                attempt=retries,
                error=error[:300],
            )
            try:
                raw_output = tools.tool_repair_plan(self.client, requirement, raw_output)
            except ToolFailureError as e:
                self.logger.log("tool_failure", tool="repair_plan", error=str(e))
                return self._escalate_tool_failure(run_id, requirement, str(e), retries)

            state = WorkerState.VALIDATING
            plan, error = tools.tool_validate_schema(raw_output)

        if error is not None:
            # Exhausted retries -- escalate rather than emit a broken/fabricated plan
            state = WorkerState.ESCALATED_TOOL_FAILURE
            escalation = EscalationReport(
                reason="tool_failure",
                explanation=f"Model output failed schema validation after {retries} repair attempts: {error[:300]}",
                missing_information_needed=[],
            )
            self.logger.log("escalation", reason=escalation.reason, state=state.value)
            return RunResult(run_id=run_id, final_state=state, escalation=escalation, retries_used=retries)

        # ---- OUTPUT -----------------------------------------------------
        state = WorkerState.OUTPUT
        self.logger.log(
            "output_produced",
            state=state.value,
            overall_confidence=plan.overall_confidence,
            retries_used=retries,
        )
        return RunResult(run_id=run_id, final_state=state, plan=plan, retries_used=retries)

    # -- helpers -----------------------------------------------------------

    def _escalate_tool_failure(
        self, run_id: str, requirement: str, error: str, retries: int = 0
    ) -> RunResult:
        escalation = EscalationReport(
            reason="tool_failure",
            explanation=f"A required tool call failed: {error}",
            missing_information_needed=[],
        )
        return RunResult(
            run_id=run_id,
            final_state=WorkerState.ESCALATED_TOOL_FAILURE,
            escalation=escalation,
            retries_used=retries,
        )

    @staticmethod
    def _questions_from_missing(missing: list[str]) -> list[str]:
        qmap = {
            "actor/user role": "Who is the primary user/actor for this feature?",
            "concrete action/verb": "What specific action should the user be able to take?",
            "sufficient detail (requirement too short)": "Can you expand this requirement with more detail (goal, actor, and desired outcome)?",
        }
        return [qmap.get(m, f"Please clarify: {m}") for m in missing]

    def submit_feedback(self, requirement: str, corrected_plan: dict) -> None:
        """Feedback loop entry point -- a human-corrected plan becomes an exemplar."""
        self.memory.add_feedback(requirement, corrected_plan)
        self.logger.log("feedback_ingested", requirement=requirement)
