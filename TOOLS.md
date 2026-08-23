# TOOLS.md — Tool Contracts

Every tool has one job, a typed input, a typed output, and a documented
failure mode. The orchestrator (`src/worker.py`) never talks to the LLM
client directly — only through these named tools — so each decision point
is independently testable and independently loggable.

---

### `classify_completeness`

**File:** `src/tools.py::tool_classify_completeness`

- **Input:** raw requirement text (`str`)
- **Output:** `CompletenessReport`
  ```
  completeness_score: float [0-1]
  missing_critical_elements: [str]
  detected_actor: str | null
  detected_core_entity: str | null
  contradictions: [str]
  should_escalate: bool
  reasoning: str
  ```
- **Failure mode:** raises `ToolFailureError` on network/API failure →
  orchestrator escalates immediately with reason `tool_failure`.
- **Contract:** must NOT invent an actor/entity that isn't implied by the
  text — absence must be reported as `MISSING`, not filled in.

---

### `generate_plan`

**File:** `src/tools.py::tool_generate_plan`

- **Input:** requirement text (`str`), list of similar past exemplars (`list`)
- **Output:** raw text (`str`) — **not yet validated**. The caller must run
  it through `validate_schema` before trusting it.
- **Failure mode:** raises `ToolFailureError` on network/API failure.
- **Contract:** only called after `classify_completeness` has returned
  `should_escalate = False`. Never called directly for ambiguous input.

---

### `repair_plan`

**File:** `src/tools.py::tool_repair_plan`

- **Input:** requirement text (`str`), the previous broken output (`str`)
- **Output:** raw text (`str`) — again, unvalidated until re-checked.
- **Failure mode:** raises `ToolFailureError`.
- **Contract:** called at most `MAX_RETRIES = 2` times per run (see
  `src/worker.py`). After that, the orchestrator escalates with reason
  `tool_failure` rather than retrying indefinitely — a deliberate cost and
  reliability guardrail.

---

### `validate_schema`

**File:** `src/tools.py::tool_validate_schema`

- **Input:** raw text (`str`)
- **Output:** `(RequirementPlan | None, error: str | None)`
- **Failure mode:** does not raise — returns `(None, error_message)` on
  invalid JSON or schema mismatch, so the caller can decide to retry.
- **Contract:** this is the single gate between "text a model produced"
  and "structured data the rest of the system trusts." Nothing downstream
  ever sees unvalidated output.

---

### `ExemplarStore` (memory tool)

**File:** `src/memory.py`

- `add_feedback(requirement, corrected_plan)` — append a human correction.
- `top_k_similar(requirement, k)` — retrieve the `k` most similar past
  corrections via keyword-overlap similarity (cheap, explainable, no
  embedding API calls).
- **Contract:** this is the worker's only form of persistent memory. It is
  a flat, human-readable JSON file (`memory_store/exemplars.json`) by
  design — auditable with a text editor, no database required.

---

### `AuditLogger` (logging tool)

**File:** `src/audit_log.py`

- `log(event, **data)` — append one structured JSON line to
  `logs/<run_id>.jsonl`.
- **Contract:** append-only, one file per run, human-readable. Every state
  transition, tool call, and escalation decision is logged. This is the
  audit trail an evaluator or ops reviewer reads to answer "why did the
  worker do that?" without needing to ask the worker.

---

## Tool call sequence (happy path)

```
classify_completeness
      |  (should_escalate = False)
      v
generate_plan
      |
      v
validate_schema --(invalid)--> repair_plan --> validate_schema  (x up to 2)
      |  (valid)
      v
[ output logged, RunResult returned ]
```
