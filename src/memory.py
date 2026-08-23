"""
Memory / feedback-loop strategy.

The worker has no long-term "memory" in the sense of a vector DB -- that
would be over-engineering for a bounded workflow like this. Instead it uses
a simple, auditable JSON exemplar store:

  - Every time a human corrects a generated plan, the corrected
    (requirement -> plan) pair is appended to memory_store/exemplars.json.
  - On future runs, the worker retrieves the top-K most similar past
    exemplars (keyword overlap similarity -- cheap, explainable, no
    embedding API calls needed) and includes them as few-shot context.

This keeps "memory" fully inspectable and diffable in git, which matters
for audit purposes -- an evaluator (or a future engineer) can literally
read memory_store/exemplars.json to see everything the worker has "learned".
"""
from __future__ import annotations

import json
import os
from typing import List, Dict, Any

DEFAULT_PATH = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "memory_store",
    "exemplars.json",
)


class ExemplarStore:
    def __init__(self, path: str = DEFAULT_PATH):
        self.path = path
        if not os.path.exists(self.path):
            os.makedirs(os.path.dirname(self.path), exist_ok=True)
            with open(self.path, "w") as f:
                json.dump([], f)

    def all(self) -> List[Dict[str, Any]]:
        with open(self.path) as f:
            return json.load(f)

    def add_feedback(self, requirement: str, corrected_plan: Dict[str, Any]) -> None:
        exemplars = self.all()
        exemplars.append({"requirement": requirement, "corrected_plan": corrected_plan})
        with open(self.path, "w") as f:
            json.dump(exemplars, f, indent=2)

    def top_k_similar(self, requirement: str, k: int = 2) -> List[Dict[str, Any]]:
        """Cheap keyword-overlap similarity. No embeddings, no API cost."""
        exemplars = self.all()
        if not exemplars:
            return []
        req_words = set(requirement.lower().split())

        def score(ex):
            ex_words = set(ex["requirement"].lower().split())
            if not ex_words:
                return 0
            return len(req_words & ex_words) / len(req_words | ex_words)

        ranked = sorted(exemplars, key=score, reverse=True)
        return ranked[:k]
