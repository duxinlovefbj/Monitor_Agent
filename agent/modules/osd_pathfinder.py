from __future__ import annotations

from pathlib import Path
from typing import Iterable

from demo.lib.app.path_finder import OSDMenuPathfinder


class OSDNavigator:
    """Thin adapter over legacy OSD pathfinder for agent execution."""

    def __init__(self, json_path: str | None = None):
        self._pathfinder = OSDMenuPathfinder(json_path=json_path)

    def load_json(self, json_path: str) -> None:
        self._pathfinder.update_data(json_path)

    def navigate_path(self, path: Iterable[str], start_path: Iterable[str] | None = None) -> dict:
        target = tuple(path)
        start = tuple(start_path or ())

        code, route = self._pathfinder.find_shortest_path(start, target)
        return {
            "status": code,
            "target": list(target),
            "steps": [{"action": action, "next_state": next_state} for action, next_state in route],
        }

    @staticmethod
    def ensure_json_exists(json_path: str) -> None:
        if not Path(json_path).exists():
            raise FileNotFoundError(f"OSD JSON 不存在: {json_path}")
