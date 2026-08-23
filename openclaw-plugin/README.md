# OpenClaw Plugin: Requirement Planner

This is a real OpenClaw tool plugin, generated with `openclaw plugins init` and
compiled against the actual `openclaw` npm package (`openclaw@2026.7.1-2`).
It exposes the existing, independently-tested Python Requirement Planner
Worker (see `../reqplanner`) as two OpenClaw tools:

- **`plan_requirement`** — takes a raw requirement, returns a structured
  plan or an escalation report.
- **`submit_plan_feedback`** — feeds a human-corrected plan back into the
  worker's exemplar memory.

## Why a plugin wraps the Python worker instead of reimplementing it in TS

The Python worker (`reqplanner/`) already has its own tested state machine,
schema validation, retry/repair logic, and audit logging — reimplementing
all of that in TypeScript would duplicate logic and duplicate bugs. This
plugin's job is narrower and more honest about what it is: **expose an
existing, verified tool to OpenClaw's agent runtime**, the same way you'd
wrap any external service as a tool. OpenClaw's runtime handles the
conversation loop, session state, and messaging-channel delivery; the
worker keeps owning the actual planning logic.

## What's actually verified vs. what isn't

Honest status, so nobody (including me) overclaims this in an interview:

✅ **Verified:**
- The plugin scaffold was generated with the real `openclaw plugins init`
  command, not hand-written from a guess at the format.
- `npm run build` compiles cleanly against `openclaw/plugin-sdk/tool-plugin`
  — no type errors against the real SDK.
- The compiled module loads in Node and exposes correct tool metadata
  (`requirement-planner` / `plan_requirement` / `submit_plan_feedback`).
- The exact subprocess-call logic used inside `execute()` was run directly
  and correctly invokes the Python worker and gets back both a full plan
  (happy path) and an escalation report (ambiguous-input path).

❌ **Not verified (documented limitation, not hidden):**
- `openclaw plugins validate` itself refused to run in this environment
  because it requires Node >=22.22.3/24.15.0/25.9.0, and only Node 22.22.2
  was available via apt with no route to a newer Node binary (this sandbox's
  network allowlist doesn't include nodejs.org). The TypeScript compiles
  and the handler logic works when called directly — but the plugin has
  **not** been loaded and run inside a live OpenClaw Gateway process.
- No messaging channel (WhatsApp/Slack/etc.) has been wired up — this
  would require real channel credentials.
- No live OpenClaw agent turn (`openclaw agent --local --message ...`) has
  been executed against a real model, since that also needs the newer
  Node runtime plus an LLM provider API key.

## To actually run this for real

```bash
# 1. Use Node >=22.22.3 (or 24.x / 25.x)
nvm install 24 && nvm use 24

# 2. Install and build
npm install
npm run plugin:build
npm run plugin:validate

# 3. Point it at your reqplanner checkout (defaults to /home/claude/reqplanner)
export REQPLANNER_PATH=/path/to/reqplanner

# 4. Register it with a real OpenClaw workspace
openclaw setup --wizard   # or --non-interactive --accept-risk --workspace <dir>
openclaw plugins install ./  # install this plugin from the local path

# 5. Run an agent turn locally, using the tool
openclaw agent --local --message "Plan this requirement: as a customer I want a wishlist" \
  --model anthropic/claude-sonnet-4-6
```

## Files

- `src/index.ts` — the two tool definitions
- `openclaw.plugin.json` — plugin manifest (id, tool contract list)
- `package.json` — build/validate/test scripts, real `openclaw` peer dependency
