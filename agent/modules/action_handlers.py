from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any

from agent.test_executor import TestExecutor
from .ca410_actions import measure_ca410
from .key_actions import press_osd_key
from .osd_pathfinder import OSDNavigator
from .pattern_actions import show_pattern


@dataclass
class AgentActionHandlers:
    """Migrated capabilities from demo/lib, exposed as composable handlers."""

    osd_json_path: str | None = None
    manufacturer: str = "KTC"
    osd_navigator: OSDNavigator = field(init=False)

    def __post_init__(self):
        self.osd_navigator = OSDNavigator(self.osd_json_path)

    def navigate_osd(self, path: list[str], start_path: list[str] | None = None, set_value: str | None = None) -> dict:
        result = self.osd_navigator.navigate_path(path=path, start_path=start_path)
        if set_value is not None:
            result["set_value"] = set_value
        return result

    def press_key(self, key: str, duration: str = "short") -> dict:
        action_name = f"长按{key}" if duration.lower() == "long" and not key.startswith("长按") else key
        return press_osd_key(action_name, manufacturer=self.manufacturer)

    def show_test_pattern(self, pattern: str) -> dict:
        return show_pattern(pattern)

    def measure_ca410(self, label: str = "", zero_cal_before_measure: bool = False) -> dict:
        return measure_ca410(zero_cal_before_measure=zero_cal_before_measure, label=label)

    @staticmethod
    def enable_hdr(enabled: bool, mode: str = "") -> dict:
        # Placeholder for system integration (e.g. Win+Alt+B).
        state = "ON" if enabled else "OFF"
        return {"hdr": state, "mode": mode}

    @staticmethod
    def wait_human(instruction: str, timeout_sec: float = 0.0) -> dict:
        if timeout_sec > 0:
            time.sleep(timeout_sec)
        return {"instruction": instruction, "waited_sec": timeout_sec}

    @staticmethod
    def calculate_color_gamut(measurements: dict | None = None) -> dict:
        # Keep this placeholder modular; caller can replace with real calculator.
        return {"CIE1931": 99.5, "CIE1976": 97.2, "inputs": measurements or {}}

    @staticmethod
    def record_result(label: str, source: str = "") -> dict:
        return {"label": label, "source": source}


def build_default_executor(handlers: AgentActionHandlers) -> TestExecutor:
    """Build an executor with migrated modules pre-registered."""
    return (
        TestExecutor()
        .register("navigate_osd", handlers.navigate_osd)
        .register("press_key", handlers.press_key)
        .register("show_test_pattern", handlers.show_test_pattern)
        .register("measure_ca410", handlers.measure_ca410)
        .register("enable_hdr", handlers.enable_hdr)
        .register("wait_human", handlers.wait_human)
        .register("calculate_color_gamut", handlers.calculate_color_gamut)
        .register("record_result", handlers.record_result)
    )
