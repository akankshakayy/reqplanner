"""
Tests covering the worker's four core execution paths:
1. Happy path -> OUTPUT with a valid plan
2. Ambiguous requirement -> ESCALATED_AMBIGUOUS, no plan fabricated
3. Malformed LLM output -> retried and repaired -> OUTPUT
4. Tool/network failure -> ESCALATED_TOOL_FAILURE
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.worker import RequirementPlannerWorker
from src.llm_client import MockReasoningClient
from src.memory import ExemplarStore
from src.audit_log import AuditLogger
from src.schemas import WorkerState


CLEAR_REQUIREMENT = (
    "As a customer, I want to save products to a wishlist so I can buy them later."
)
AMBIGUOUS_REQUIREMENT = "Build a feature for saving stuff."


def make_worker(client):
    return RequirementPlannerWorker(
        client=client,
        memory=ExemplarStore(path="/tmp/test_exemplars.json"),
        logger=AuditLogger(run_id="test-run"),
    )


def test_happy_path_produces_plan():
    worker = make_worker(MockReasoningClient())
    result = worker.run(CLEAR_REQUIREMENT)
    assert result.final_state == WorkerState.OUTPUT
    assert result.plan is not None
    assert result.escalation is None
    assert result.plan.overall_confidence > 0
    assert len(result.plan.api_endpoints) > 0
    assert len(result.plan.db_tables) > 0
    assert len(result.plan.test_cases) > 0


def test_ambiguous_requirement_escalates_without_plan():
    worker = make_worker(MockReasoningClient())
    result = worker.run(AMBIGUOUS_REQUIREMENT)
    assert result.final_state == WorkerState.ESCALATED_AMBIGUOUS
    assert result.plan is None, "Worker must NOT fabricate a plan for an ambiguous requirement"
    assert result.escalation is not None
    assert len(result.escalation.suggested_clarifying_questions) > 0


def test_malformed_output_is_repaired_via_retry():
    worker = make_worker(MockReasoningClient(fail_mode="malformed_once"))
    result = worker.run(CLEAR_REQUIREMENT)
    assert result.final_state == WorkerState.OUTPUT
    assert result.retries_used == 1
    assert result.plan is not None


def test_tool_failure_escalates_gracefully():
    worker = make_worker(MockReasoningClient(fail_mode="tool_failure"))
    result = worker.run(CLEAR_REQUIREMENT)
    assert result.final_state == WorkerState.ESCALATED_TOOL_FAILURE
    assert result.plan is None
    assert result.escalation.reason == "tool_failure"


def test_feedback_loop_adds_exemplar():
    store = ExemplarStore(path="/tmp/test_exemplars_feedback.json")
    before = len(store.all())
    store.add_feedback(CLEAR_REQUIREMENT, {"requirement_summary": "corrected"})
    after = len(store.all())
    assert after == before + 1


def test_exemplars_improve_similarity_retrieval():
    store = ExemplarStore(path="/tmp/test_exemplars_sim.json")
    store.add_feedback(CLEAR_REQUIREMENT, {"requirement_summary": "wishlist plan"})
    similar = store.top_k_similar("As a customer I want to manage my wishlist", k=1)
    assert len(similar) == 1


if __name__ == "__main__":
    import pytest
    raise SystemExit(pytest.main([__file__, "-v"]))
