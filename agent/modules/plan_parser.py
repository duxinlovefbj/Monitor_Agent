from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass
class ParsedStep:
    id: int
    action: str
    params: dict[str, Any]
    description: str


def parse_plan(raw_plan: dict[str, Any]) -> list[ParsedStep]:
    """Normalize LLM plan into typed steps for downstream execution."""
    steps = raw_plan.get("steps", [])
    parsed: list[ParsedStep] = []

    for idx, step in enumerate(steps, start=1):
        parsed.append(
            ParsedStep(
                id=int(step.get("id", idx)),
                action=str(step.get("action", "")).strip(),
                params=step.get("params", {}) or {},
                description=str(step.get("description", "")).strip(),
            )
        )
    return parsed
