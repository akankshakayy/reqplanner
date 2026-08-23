"""
Audit/logging approach.

Every run writes one JSONL file: logs/<run_id>.jsonl
Each line is a single structured event: state transitions, tool calls,
decisions, and their confidence/reasoning. This is deliberately append-only
and human-readable (not a binary trace format) so it can be reviewed by a
non-engineer (ops/product) during the evaluation, per Eko's stated
requirement for an "audit trail".
"""
from __future__ import annotations

import json
import os
import time
import uuid
from typing import Any, Dict

LOG_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "logs"
)


class AuditLogger:
    def __init__(self, run_id: str | None = None):
        self.run_id = run_id or str(uuid.uuid4())[:8]
        os.makedirs(LOG_DIR, exist_ok=True)
        self.path = os.path.join(LOG_DIR, f"{self.run_id}.jsonl")

    def log(self, event: str, **data: Any) -> None:
        record: Dict[str, Any] = {
            "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "run_id": self.run_id,
            "event": event,
            **data,
        }
        with open(self.path, "a") as f:
            f.write(json.dumps(record) + "\n")
