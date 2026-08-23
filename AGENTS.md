# AGENTS.md — Full-Stack Requirement Planner Worker

This file is the single source of truth for how this AI Worker is scoped,
what it is allowed to decide on its own, and when it must stop.

## Goal

Given a raw, human-written product requirement, produce a structured,
developer-ready technical plan — frontend pages, backend API contracts,
database schema, validation rules, edge cases, and test cases — so that a
PM's one-paragraph requirement becomes something an engineer can start
building from without a clarification meeting.

## User

Product managers, founders, or engineering leads who write requirements in
plain language and need a fast, consistent first-pass technical breakdown
before an engineer picks up the work.

## System (where this sits in a larger workflow)

```
PM writes requirement
        |
        v
[ Requirement Planner Worker ]  <-- this project
        |
        +--> clean plan  --> engineer starts implementation
        |
        +--> escalation   --> PM answers clarifying questions, resubmits
```

It is a pre-development step. It does not write code, does not deploy
anything, and does not talk to production systems. Its only output is a
document (JSON plan) or a clarification request.

## Inputs

- A raw text requirement (string), typically 1 sentence to 1 short paragraph.
- Optionally, past human-corrected plans for similar requirements (pulled
  automatically from `memory_store/exemplars.json`).

## Decisions the worker CAN make autonomously

- Whether a requirement has enough information to plan from, or must be
  escalated (see `TOOLS.md` → `classify_completeness`).
- What frontend pages, API endpoints, DB tables, validations, edge cases,
  and test cases are implied by a sufficiently clear requirement.
- Whether to retry its own malformed output before giving up.
- Which past exemplars are relevant enough to reuse as few-shot context.

## Outputs

- **Success**: a `RequirementPlan` JSON object (see `src/schemas.py`).
- **Escalation**: an `EscalationReport` JSON object — never a fabricated
  plan.
- An append-only audit log of every decision made along the way
  (`logs/<run_id>.jsonl`).

## Constraints — what this worker must NOT do

1. It must **never** invent a core actor, entity, or business rule that
   isn't implied by the requirement text. If it has to guess, it must
   record the guess as a flagged, confidence-scored `Assumption` — never
   present a guess as a fact.
2. It must **never** emit a full plan for a requirement it has classified
   as ambiguous or contradictory. Escalation happens *before* planning.
3. It must **never** silently swallow a tool failure (e.g. a broken API
   call) and return a partial/guessed result — it escalates instead.
4. It does not have write access to any real codebase, ticket system, or
   production data. It only reads a requirement and writes a plan document.
5. It caps automatic repair attempts at 2 retries — after that it escalates
   rather than looping indefinitely (cost + reliability guardrail).

## Feedback loop

Humans can correct a generated plan and submit it back:

```
python -m src.cli feedback --file <requirement.txt> --plan <corrected_plan.json>
```

This is appended to `memory_store/exemplars.json`. On future runs, the
worker retrieves the most similar past corrections (cheap keyword-overlap
similarity — no embedding API calls) and includes them as few-shot context
in the planning prompt, so its output drifts toward the team's real
conventions over time.

## Escalation policy

The worker stops and asks a human when:

| Condition | Escalation reason |
|---|---|
| Requirement is missing a clear actor/user role | `ambiguous_requirement` |
| Requirement is missing a concrete action/verb | `ambiguous_requirement` |
| Requirement is too short to extract meaningful intent | `ambiguous_requirement` |
| Requirement contains detectable self-contradictions | `contradiction` |
| A required tool call fails (network/API) | `tool_failure` |
| Model output fails schema validation after 2 repair attempts | `tool_failure` |

See `TOOLS.md` for exact tool contracts and `SOUL.md` for the reasoning
principles behind these choices.

## What the current version does autonomously

- Classifies whether a requirement is plannable.
- Generates a full plan (pages/APIs/DB/tests) for well-formed requirements.
- Retries and repairs its own malformed output up to twice.
- Escalates cleanly (with specific clarifying questions) instead of
  guessing, for both ambiguous input and tool failures.
- Logs every decision to an inspectable audit trail.
- Ingests human feedback into a growing exemplar memory.

## What the next version would improve

- Replace keyword-overlap exemplar similarity with a lightweight embedding
  index once volume justifies the added cost.
- Add a second classifier pass for **scope estimation** (t-shirt sizing)
  once enough human-corrected plans exist to calibrate against.
- Add a "conflicting requirement vs. existing system" check by giving the
  worker read access to an existing schema/OpenAPI spec, so it can flag
  requirements that conflict with what's already built — not just
  internally-contradictory text.
- Swap `MockReasoningClient` for `AnthropicClient` by default once this
  moves from evaluation into a real internal tool, with per-run cost
  logging added to the audit trail.
