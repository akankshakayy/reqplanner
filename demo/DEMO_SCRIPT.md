# Demo Video Script

Aim for 3–5 minutes. Record your terminal (e.g. with QuickTime screen
recording, OBS, or `asciinema`). Suggested narration below each command —
say it in your own words, don't just read it.

---

**1. Introduce the worker (15s)**

> "This is a Full-Stack Requirement Planner Worker. It takes a raw product
> requirement and turns it into a structured technical plan — or, if the
> requirement isn't clear enough, it stops and asks a specific question
> instead of guessing."

**2. Show the architecture briefly (30s)**

Open `AGENTS.md` and scroll through the Goal/User/System/Constraints
sections. Then open `src/worker.py` and point at the state machine
docstring at the top.

> "It's a state machine: intake, classify, then either escalate or plan,
> validate, and retry up to twice before falling back to escalation."

**3. Run the happy path (45s)**

```bash
python -m src.cli run --file examples/input_1_clear.txt
```

> "Here's a clear requirement — 'customer saves products to a wishlist'.
> The worker classifies it as complete, generates a full plan: frontend
> pages, API endpoints, DB schema, validation rules, edge cases, and test
> cases. Notice every inferred detail is logged as an assumption with a
> confidence score, not stated as fact."

**4. Run the escalation path — the intentional failure case (45s)**

```bash
python -m src.cli run --file examples/input_2_ambiguous.txt
```

> "Now here's a deliberately vague requirement — 'build a feature for
> saving stuff'. No actor, no clear action. Instead of guessing and
> producing a plausible-looking but wrong plan, the worker escalates. It
> tells you exactly what's missing and gives you the clarifying questions
> to ask. This is the intentional failure/exception case for this demo."

**5. Run the retry/repair recovery path (30s)**

```bash
python -m src.cli run --file examples/input_1_clear.txt --inject-failure malformed_once
```

> "This flag simulates the model returning broken JSON on its first try.
> Watch — schema validation catches it, the worker asks the model to
> repair its own output, re-validates, and succeeds on retry 1. It only
> escalates if this fails twice in a row."

**6. Run the tool-failure escalation (30s)**

```bash
python -m src.cli run --file examples/input_1_clear.txt --inject-failure tool_failure
```

> "And this simulates an actual API/network failure. No crash, no silent
> empty response — a clean escalation report."

**7. Show the audit log (20s)**

```bash
cat logs/<the-most-recent-run-id>.jsonl
```

> "Every decision along the way is logged — you can reconstruct exactly
> why the worker did what it did without asking it."

**8. Show the feedback loop (30s)**

```bash
python -m src.cli feedback --file examples/input_1_clear.txt --plan examples/output_1_plan_corrected.json
cat memory_store/exemplars.json
```

> "If a human corrects a plan, I can feed that correction back in. It gets
> stored here, and future similar requirements will use it as a few-shot
> example — this is the feedback loop."

**9. Run the tests (15s)**

```bash
python -m pytest tests/ -v
```

> "And the whole thing is covered by tests for all four paths — happy
> path, escalation, retry recovery, and tool failure."

**10. Close (15s)**

> "This defaults to a free, deterministic mock reasoning engine so the
> whole pipeline is testable with zero API cost — swapping in the real
> Claude API is a one-line env var change. Full design rationale is in
> AGENTS.md, SOUL.md, and TOOLS.md in the repo."

---

Upload the recording to Google Drive / Loom / YouTube (unlisted) and link
it in your submission email alongside the GitHub repo link.
