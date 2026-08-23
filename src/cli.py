"""
CLI entrypoint.

Usage:
    python -m src.cli run "requirement text here"
    python -m src.cli run --file examples/input_1_clear.txt
    python -m src.cli run --file examples/input_2_ambiguous.txt
    python -m src.cli run --file examples/input_1_clear.txt --inject-failure malformed_once
    python -m src.cli feedback --file examples/input_1_clear.txt --plan examples/output_1_plan.json
"""
from __future__ import annotations

import argparse
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.llm_client import MockReasoningClient, AnthropicClient
from src.worker import RequirementPlannerWorker
from src.memory import ExemplarStore
from src.audit_log import AuditLogger


def build_client(inject_failure: str | None):
    backend = os.environ.get("REQPLANNER_LLM", "mock")
    if backend == "anthropic":
        return AnthropicClient()
    return MockReasoningClient(fail_mode=inject_failure)


def cmd_run(args):
    requirement = args.requirement
    if args.file:
        with open(args.file) as f:
            requirement = f.read().strip()
    if not requirement:
        print("No requirement provided.", file=sys.stderr)
        sys.exit(1)

    client = build_client(args.inject_failure)
    worker = RequirementPlannerWorker(client=client)

    result = worker.run(requirement)

    if args.json_only:
        # Machine-readable mode, e.g. for the OpenClaw tool plugin --
        # no run_id banners or separators, just the structured result.
        payload = {
            "run_id": worker.logger.run_id,
            "final_state": result.final_state.value,
            "retries_used": result.retries_used,
            "plan": result.plan.model_dump() if result.plan else None,
            "escalation": result.escalation.model_dump() if result.escalation else None,
        }
        print(json.dumps(payload))
        return

    print(f"[run_id={worker.logger.run_id}] Requirement:\n  {requirement}\n")
    print(f"Final state: {result.final_state.value}")
    print(f"Retries used: {result.retries_used}")
    print("-" * 60)

    if result.plan:
        print(json.dumps(result.plan.model_dump(), indent=2))
    if result.escalation:
        print("ESCALATED -- no plan was generated.")
        print(json.dumps(result.escalation.model_dump(), indent=2))

    print("-" * 60)
    print(f"Audit log written to: logs/{worker.logger.run_id}.jsonl")


def cmd_feedback(args):
    with open(args.file) as f:
        requirement = f.read().strip()
    with open(args.plan) as f:
        corrected_plan = json.load(f)

    worker = RequirementPlannerWorker(client=MockReasoningClient())
    worker.submit_feedback(requirement, corrected_plan)
    print("Feedback ingested into memory_store/exemplars.json")


def main():
    parser = argparse.ArgumentParser(description="Full-Stack Requirement Planner Worker")
    sub = parser.add_subparsers(dest="command", required=True)

    run_p = sub.add_parser("run", help="Run the worker on a requirement")
    run_p.add_argument("requirement", nargs="?", default=None)
    run_p.add_argument("--file", help="Read requirement from a text file")
    run_p.add_argument(
        "--inject-failure",
        choices=["malformed_once", "tool_failure"],
        default=None,
        help="Demo flag: force the mock client to simulate a failure",
    )
    run_p.add_argument(
        "--json-only",
        action="store_true",
        help="Print only a single-line JSON result (for programmatic callers, e.g. the OpenClaw plugin)",
    )
    run_p.set_defaults(func=cmd_run)

    fb_p = sub.add_parser("feedback", help="Submit a human-corrected plan as an exemplar")
    fb_p.add_argument("--file", required=True, help="Original requirement text file")
    fb_p.add_argument("--plan", required=True, help="Corrected plan JSON file")
    fb_p.set_defaults(func=cmd_feedback)

    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
