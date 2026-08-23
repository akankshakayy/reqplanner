# Full-Stack Requirement Planner Worker

An AI Worker that takes a raw product requirement and turns it into a
structured, developer-ready technical plan — or, if the requirement isn't
clear enough to plan safely, stops and asks the specific clarifying
questions a human needs to answer first.

Built for Eko's internship evaluation assignment.

> 📄 Full role/system definition: [`AGENTS.md`](./AGENTS.md)
> 🧭 Reasoning principles: [`SOUL.md`](./SOUL.md)
> 🔧 Tool contracts: [`TOOLS.md`](./TOOLS.md)

---

## Why this workflow

Eko's brief was explicit that this shouldn't be a chatbot, a RAG demo, or a
thin wrapper around an API call — it should show understanding of a real
business workflow. The workflow here: **a PM writes a one-paragraph
requirement, and an engineer needs a technical breakdown before they can
start building.** That translation step is repetitive, is done by hand
today, and has a very clear "should I proceed or should I ask a question
first" decision point — which is exactly the kind of bounded, judgment-
requiring workflow the brief asks for.

## Goal / System / User (short version — full version in `AGENTS.md`)

- **Goal:** turn a raw requirement into a structured plan, safely.
- **User:** PMs, founders, engineering leads.
- **System:** sits between "requirement written" and "engineer starts
  building" — a pre-development step, not a deployment step.
- **Constraint:** never fabricate a plan for an under-specified requirement.

## Quickstart

```bash
cd reqplanner
pip install -r requirements.txt

# Happy path -- clear requirement produces a full plan
python -m src.cli run --file examples/input_1_clear.txt

# Escalation path -- ambiguous requirement is refused, not guessed at
python -m src.cli run --file examples/input_2_ambiguous.txt

# Failure-handling demo -- forces a malformed first response,
# watch it self-repair and recover
python -m src.cli run --file examples/input_1_clear.txt --inject-failure malformed_once

# Failure-handling demo -- forces a simulated tool/network failure,
# watch it escalate cleanly instead of crashing or guessing
python -m src.cli run --file examples/input_1_clear.txt --inject-failure tool_failure

# Feedback loop -- teach the worker from a human correction
python -m src.cli feedback --file examples/input_1_clear.txt --plan examples/output_1_plan_corrected.json

# Run the test suite
python -m pytest tests/ -v
```

Every run prints its `run_id` and writes a full audit trail to
`logs/<run_id>.jsonl`.

## Zero-cost by default

The worker runs on a deterministic, rule-based `MockReasoningClient` unless
you explicitly opt into the real Claude API:

```bash
export REQPLANNER_LLM=anthropic
export ANTHROPIC_API_KEY=sk-...
python -m src.cli run "your requirement here"
```

This is a deliberate design choice, not a limitation — see `SOUL.md` §3
("Cost is a constraint, not an afterthought"). The mock engine exists to
let anyone (including an evaluator) run and test the full state machine —
classification, planning, retry/repair, escalation, memory, and audit
logging — with zero setup and zero API spend. The architecture underneath
is identical either way; only the reasoning backend changes.

## Project structure

```
reqplanner/
├── AGENTS.md              # goal, system, decisions, constraints, escalation policy
├── SOUL.md                # reasoning principles
├── TOOLS.md                # tool contracts
├── README.md               # this file
├── requirements.txt
├── src/
│   ├── schemas.py           # typed data contracts (Pydantic)
│   ├── llm_client.py         # mock (default) + real Anthropic backend
│   ├── memory.py              # exemplar store / feedback loop
│   ├── audit_log.py            # JSONL audit trail
│   ├── tools.py                  # named tool functions
│   ├── worker.py                  # the state machine orchestrator
│   └── cli.py                      # command-line entrypoint
├── examples/                # sample inputs + captured outputs for all 4 scenarios
├── tests/                   # pytest suite covering all execution paths
├── memory_store/            # exemplars.json (grows as feedback is submitted)
├── logs/                    # audit logs, one JSONL file per run
└── demo/
    └── DEMO_SCRIPT.md       # narration script for the demo video
```

## State machine

```
INTAKE -> CLASSIFY -> (ESCALATE | PLAN) -> VALIDATE -> (RETRY x2 max | OUTPUT)
```

Full diagram and rationale in `src/worker.py` module docstring and
`AGENTS.md`.

## The intentional failure case (per the assignment brief)

Two are included, on purpose, because they demonstrate different failure
categories:

1. **Ambiguous input** (`examples/input_2_ambiguous.txt`) — the worker
   detects a missing actor and missing action, and escalates with specific
   clarifying questions instead of guessing at a plan.
2. **Tool failure** (`--inject-failure tool_failure`) — simulates an
   API/network failure and shows the worker escalating cleanly rather than
   crashing or silently returning nothing.

A third scenario (`--inject-failure malformed_once`) shows the *recovery*
path — a malformed model response gets caught by schema validation and
repaired via retry, succeeding on the second attempt. This is included to
show the worker doesn't escalate on every hiccup — only when it genuinely
can't recover.

## What's autonomous now vs. what's next

See the bottom of `AGENTS.md` for the full list. Short version: the worker
fully owns classification → planning → validation → retry → escalation →
logging → feedback ingestion today. The next version would add scope
(t-shirt size) estimation and the ability to check a new requirement
against an existing system's real schema, not just against itself.
