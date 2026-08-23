"""
LLM client abstraction.

Design decision (documented for evaluators): the worker defaults to a
deterministic, rule-based MockReasoningClient so the entire pipeline is
runnable with ZERO API cost and ZERO setup. This is a deliberate
"cost awareness" and "responsible use of AI" choice -- we do not want a
demo/eval script silently burning API credits every time someone runs it.

Swap in the real AnthropicClient by setting:
    export REQPLANNER_LLM=anthropic
    export ANTHROPIC_API_KEY=sk-...

Both clients implement the same interface: .complete(system, user) -> str
"""
from __future__ import annotations

import json
import os
import re
from abc import ABC, abstractmethod


class LLMClient(ABC):
    @abstractmethod
    def complete(self, system: str, user: str) -> str:
        ...


class ToolFailureError(Exception):
    """Raised by clients to simulate/represent a tool/network failure."""


class AnthropicClient(LLMClient):
    """Real Claude API backend. Requires `pip install anthropic` and an API key."""

    def __init__(self, model: str = "claude-sonnet-4-6"):
        try:
            import anthropic
        except ImportError as e:
            raise RuntimeError(
                "anthropic package not installed. Run: pip install anthropic"
            ) from e
        api_key = os.environ.get("ANTHROPIC_API_KEY")
        if not api_key:
            raise RuntimeError("ANTHROPIC_API_KEY not set in environment.")
        self._client = anthropic.Anthropic(api_key=api_key)
        self._model = model

    def complete(self, system: str, user: str) -> str:
        try:
            resp = self._client.messages.create(
                model=self._model,
                max_tokens=2000,
                system=system,
                messages=[{"role": "user", "content": user}],
            )
            return "".join(
                block.text for block in resp.content if block.type == "text"
            )
        except Exception as e:  # network error, rate limit, etc.
            raise ToolFailureError(f"Anthropic API call failed: {e}") from e


class MockReasoningClient(LLMClient):
    """
    Deterministic, rule-based stand-in for an LLM.

    This is NOT meant to be a good requirement planner -- it's meant to
    exercise the full state machine (classify -> plan -> validate -> retry
    -> escalate) reproducibly, without network access or API cost, so the
    architecture can be evaluated on its own merits.

    It can also be told to inject failures on purpose, to demonstrate the
    worker's exception-handling and retry logic (see fail_mode).
    """

    def __init__(self, fail_mode: str | None = None):
        # fail_mode: None | "malformed_once" | "tool_failure"
        self.fail_mode = fail_mode
        self._malformed_already_sent = False

    def complete(self, system: str, user: str) -> str:
        if self.fail_mode == "tool_failure":
            raise ToolFailureError("Simulated tool failure (network timeout).")

        if "CLASSIFY_TASK" in system:
            return self._classify(user)
        if "PLAN_TASK" in system:
            if self.fail_mode == "malformed_once" and not self._malformed_already_sent:
                self._malformed_already_sent = True
                # Return deliberately broken JSON to exercise the repair/retry path
                return '{"requirement_summary": "broken json missing closing brace"'
            return self._plan(user)
        raise ValueError("Unknown task type for MockReasoningClient")

    # -- naive heuristics standing in for LLM understanding -----------------

    _ACTOR_WORDS = ["user", "customer", "admin", "agent", "merchant", "operator",
                    "manager", "partner", "employee", "buyer", "seller", "member"]
    _ACTION_WORDS = ["create", "view", "edit", "update", "delete", "search",
                     "book", "track", "save", "manage", "upload", "approve",
                     "review", "cancel", "pay", "checkout", "browse", "wishlist",
                     "subscribe", "notify"]

    def _classify(self, requirement: str) -> str:
        text = requirement.lower()
        actor = next((w for w in self._ACTOR_WORDS if w in text), None)
        action = next((w for w in self._ACTION_WORDS if w in text), None)

        missing = []
        if not actor:
            missing.append("actor/user role")
        if not action:
            missing.append("concrete action/verb")
        if len(text.split()) < 6:
            missing.append("sufficient detail (requirement too short)")

        contradictions = []
        if "no login" in text and "user account" in text:
            contradictions.append("mentions both 'no login' and 'user account'")

        score = 1.0
        score -= 0.35 * len(missing)
        score = max(0.0, min(1.0, score))

        should_escalate = score < 0.5 or bool(contradictions)

        result = {
            "completeness_score": round(score, 2),
            "missing_critical_elements": missing,
            "detected_actor": actor,
            "detected_core_entity": action,
            "contradictions": contradictions,
            "should_escalate": should_escalate,
            "reasoning": (
                f"actor={'found:' + actor if actor else 'MISSING'}, "
                f"action={'found:' + action if action else 'MISSING'}, "
                f"word_count={len(text.split())}"
            ),
        }
        return json.dumps(result)

    def _plan(self, requirement: str) -> str:
        text = requirement.lower()
        actor = next((w for w in self._ACTOR_WORDS if w in text), "user")
        action = next((w for w in self._ACTION_WORDS if w in text), "manage")
        entity = self._guess_entity(text)

        plan = {
            "requirement_summary": f"{actor.capitalize()}s can {action} {entity}.",
            "frontend_pages": [
                {
                    "name": f"{entity.capitalize()} List Page",
                    "purpose": f"Lets the {actor} browse/{action} {entity}.",
                    "key_components": [f"{entity}Card", "SearchBar", "FilterPanel"],
                    "confidence": 0.75,
                },
                {
                    "name": f"{entity.capitalize()} Detail Page",
                    "purpose": f"Shows a single {entity} and lets the {actor} {action} it.",
                    "key_components": [f"{entity}DetailView", "ActionButtons"],
                    "confidence": 0.7,
                },
            ],
            "api_endpoints": [
                {
                    "method": "GET",
                    "path": f"/api/{entity}s",
                    "description": f"List {entity}s for the {actor}.",
                    "request_fields": ["page", "filter"],
                    "response_fields": ["id", "name", "status"],
                    "confidence": 0.75,
                },
                {
                    "method": "POST",
                    "path": f"/api/{entity}s/{{id}}/{action}",
                    "description": f"{action.capitalize()} a {entity} on behalf of the {actor}.",
                    "request_fields": ["id", f"{actor}_id"],
                    "response_fields": ["status", "updated_at"],
                    "confidence": 0.65,
                },
            ],
            "db_tables": [
                {
                    "name": f"{entity}s",
                    "columns": [
                        {"name": "id", "type": "UUID", "constraints": ["PRIMARY KEY"]},
                        {"name": "name", "type": "VARCHAR(255)", "constraints": ["NOT NULL"]},
                        {"name": "status", "type": "VARCHAR(50)", "constraints": ["NOT NULL", "DEFAULT 'active'"]},
                        {"name": f"{actor}_id", "type": "UUID", "constraints": [f"FOREIGN KEY -> {actor}s.id"]},
                        {"name": "created_at", "type": "TIMESTAMP", "constraints": ["NOT NULL"]},
                    ],
                    "relations": [f"belongs_to {actor}"],
                    "confidence": 0.7,
                }
            ],
            "validation_rules": [
                {"field": "name", "rule": "required, max 255 chars"},
                {"field": f"{actor}_id", "rule": "must reference an existing, active account"},
            ],
            "edge_cases": [
                {
                    "scenario": f"{actor.capitalize()} tries to {action} a {entity} that no longer exists",
                    "expected_behavior": "Return 404 with a clear error message; do not create a partial record.",
                },
                {
                    "scenario": f"Two {actor}s attempt to {action} the same {entity} concurrently",
                    "expected_behavior": "Use optimistic locking / a version column; second writer gets a 409 conflict.",
                },
                {
                    "scenario": "Request body missing required fields",
                    "expected_behavior": "Return 400 with field-level validation errors, no partial write.",
                },
            ],
            "test_cases": [
                {
                    "name": f"test_{action}_{entity}_success",
                    "type": "integration",
                    "steps": [f"Authenticate as {actor}", f"Call POST /{entity}s/{{id}}/{action}", "Assert 200"],
                    "expected_result": f"{entity.capitalize()} status updates correctly.",
                },
                {
                    "name": f"test_{action}_{entity}_not_found",
                    "type": "integration",
                    "steps": [f"Call POST /{entity}s/does-not-exist/{action}"],
                    "expected_result": "API returns 404.",
                },
                {
                    "name": f"test_list_{entity}s_empty_state",
                    "type": "unit",
                    "steps": [f"Render {entity.capitalize()} List Page with zero {entity}s"],
                    "expected_result": "Empty-state UI is shown, not a blank/broken page.",
                },
            ],
            "assumptions": [
                {
                    "text": f"Assumed '{actor}' is the primary actor since it was the clearest role mentioned.",
                    "confidence": 0.6,
                },
                {
                    "text": "Assumed standard REST conventions since no API style was specified.",
                    "confidence": 0.7,
                },
            ],
            "overall_confidence": 0.72,
        }
        return json.dumps(plan)

    @staticmethod
    def _guess_entity(text: str) -> str:
        # very naive noun guesser for the mock -- looks for common nouns
        for w in ["order", "wishlist", "ticket", "invoice", "booking", "product",
                  "listing", "review", "subscription", "appointment", "task",
                  "document", "profile", "report"]:
            if w in text:
                return w
        m = re.search(r"\b(\w+)s\b", text)
        return m.group(1) if m else "item"
