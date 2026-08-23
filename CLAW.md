# CLAW.md — OpenClaw Integration Spec

`AGENTS.md`, `SOUL.md`, and `TOOLS.md` describe this worker in general
terms — any agent runtime could read them. This file is specific to
**OpenClaw** as the runtime: how this worker's logic is actually wired
into OpenClaw's Gateway, tool-calling loop, and session model.

If you're evaluating this without OpenClaw installed, you can skip this
file — everything it describes is a thin adapter around the
already-tested Python worker in `src/`, not new planning logic.

## Where the worker lives in OpenClaw's architecture

OpenClaw draws a hard line between the **agent runtime** (conversation
loop, session state, channel delivery — all handled by OpenClaw itself)
and **tools** (named capabilities the agent can call mid-conversation).
This worker sits entirely on the tools side:

```
User message ("plan this requirement: ...")
        |
        v
OpenClaw Gateway  --  owns the conversation loop, session_key, model calls
        |
        v
[ tool call: plan_requirement ]   <-- openclaw-plugin/src/index.ts
        |
        v
python3 -m src.cli run <requirement> --json-only   <-- the actual worker
        |
        v
RequirementPlan or EscalationReport, returned to the agent turn
```

OpenClaw's model decides *when* to call the tool and *how* to phrase the
result back to the user. It never sees or reimplements the state machine,
retry logic, or escalation policy — those stay owned by the Python worker,
single source of truth, one place to fix bugs.

## Registered tools (see `openclaw-plugin/openclaw.plugin.json`)

| Tool | Maps to | Purpose |
|---|---|---|
| `plan_requirement` | `src/cli.py run --json-only` | Runs the full worker state machine on a requirement |
| `submit_plan_feedback` | `src/cli.py feedback` | Ingests a human correction into exemplar memory |

## Agent routing

For a real deployment, this worker would run as an **isolated OpenClaw
agent** (`openclaw agents add planner --workspace ./workspace-planner`),
not the user's default personal-assistant agent — it has a narrow job and
shouldn't inherit a general assistant's personality or tool access.
Suggested binding:

```bash
openclaw agents add planner --workspace ./workspace-planner --model anthropic/claude-sonnet-4-6
openclaw plugins install ./openclaw-plugin
openclaw agents bind planner --bind slack:#product-requirements
```

That binds the planner agent to a Slack channel — a PM posts a
requirement, the agent calls `plan_requirement`, and replies in-thread
with the plan or the clarifying questions.

## What OpenClaw adds that the bare Python CLI doesn't

- **Conversation memory across turns** — if a PM replies "actually the
  actor is an admin, not a customer," OpenClaw's session state lets the
  model re-call `plan_requirement` with a clarified requirement in the
  same thread, without the human needing to restate everything.
- **Channel delivery** — the plan can land directly in Slack/WhatsApp/etc.
  instead of only being available via CLI.
- **Model routing** — swapping the underlying LLM (Claude, GPT, local
  model via Ollama) is a config change in OpenClaw, independent of this
  worker's code.

## What this worker adds that bare OpenClaw doesn't

OpenClaw is a general-purpose agent runtime — it has no opinion about
requirement planning specifically. All of the actual judgment —
classify-before-plan, escalate-before-hallucinate, schema-validated
output, capped retries, exemplar memory — is domain logic that lives in
`src/`, not in OpenClaw itself. CLAW.md exists to keep that boundary
explicit so neither side gets credit for the other's job.

## Verified vs. not (honest status — see also `openclaw-plugin/README.md`)

✅ Plugin scaffolded with real `openclaw plugins init`, compiles against
the real SDK, subprocess call path tested directly (happy path +
escalation path both confirmed).

❌ Not run inside a live OpenClaw Gateway process — this dev environment's
Node version (22.22.2) is below OpenClaw's minimum (22.22.3+), and no
messaging channel or real LLM key was available to test the full loop
end-to-end. The `agents add` / `plugins install` / `agents bind` commands
above are the correct next commands to run once on a machine with a
supported Node version — they have not been executed here.
