"""CLI wrapper for running monitor agent workflows."""

from __future__ import annotations

import argparse
import inspect
import json
import os
from pathlib import Path
from typing import Any, Callable


def _safe_invoke(func: Callable[..., Any], **kwargs: Any) -> Any:
    sig = inspect.signature(func)
    allowed = {k: v for k, v in kwargs.items() if k in sig.parameters}
    return func(**allowed)


def _normalize_params(action: str, params: dict[str, Any]) -> dict[str, Any]:
    patched = dict(params)

    if action == "navigate_osd" and "value" in patched and "set_value" not in patched:
        patched["set_value"] = str(patched.pop("value"))

    if action == "enable_hdr" and "state" in patched and "enabled" not in patched:
        patched["enabled"] = bool(patched.pop("state"))

    if action == "calculate_color_gamut" and ("mode" in patched or "source" in patched):
        mode = patched.pop("mode", "")
        source = patched.pop("source", "")
        measurements = patched.get("measurements", {})
        measurements.update({"mode": mode, "source": source})
        patched["measurements"] = measurements

    return patched


def _build_executor(handlers, mock: bool = False):
    from agent.test_executor import TestExecutor

    if mock:
        press_key = handlers.press_key
        show_test_pattern = handlers.show_test_pattern
        measure_ca410 = handlers.measure_ca410
    else:
        press_key = handlers.press_key
        show_test_pattern = handlers.show_test_pattern
        measure_ca410 = handlers.measure_ca410

    return (
        TestExecutor()
        .register("navigate_osd", lambda **kwargs: _safe_invoke(handlers.navigate_osd, **_normalize_params("navigate_osd", kwargs)))
        .register("press_key", lambda **kwargs: _safe_invoke(press_key, **kwargs))
        .register("show_test_pattern", lambda **kwargs: _safe_invoke(show_test_pattern, **kwargs))
        .register("measure_ca410", lambda **kwargs: _safe_invoke(measure_ca410, **kwargs))
        .register("enable_hdr", lambda **kwargs: _safe_invoke(handlers.enable_hdr, **_normalize_params("enable_hdr", kwargs)))
        .register("wait_human", lambda **kwargs: _safe_invoke(handlers.wait_human, **kwargs))
        .register("calculate_color_gamut", lambda **kwargs: _safe_invoke(handlers.calculate_color_gamut, **_normalize_params("calculate_color_gamut", kwargs)))
        .register("record_result", lambda **kwargs: _safe_invoke(handlers.record_result, **kwargs))
    )


class _MockHandlers:
    def navigate_osd(self, path: list[str], start_path: list[str] | None = None, set_value: str | None = None) -> dict:
        return {"mock": True, "action": "navigate_osd", "path": path, "start_path": start_path, "set_value": set_value}

    @staticmethod
    def press_key(key: str, duration: str = "short") -> dict:
        return {"mock": True, "action": "press_key", "key": key, "duration": duration}

    @staticmethod
    def show_test_pattern(pattern: str) -> dict:
        return {"mock": True, "action": "show_test_pattern", "pattern": pattern}

    @staticmethod
    def measure_ca410(label: str = "", zero_cal_before_measure: bool = False) -> dict:
        return {
            "mock": True,
            "action": "measure_ca410",
            "label": label,
            "zero_cal_before_measure": zero_cal_before_measure,
            "x": 0.3127,
            "y": 0.3290,
        }

    @staticmethod
    def enable_hdr(enabled: bool, mode: str = "") -> dict:
        return {"mock": True, "action": "enable_hdr", "enabled": enabled, "mode": mode}

    @staticmethod
    def wait_human(instruction: str, timeout_sec: float = 0.0) -> dict:
        return {"mock": True, "action": "wait_human", "instruction": instruction, "timeout_sec": timeout_sec}

    @staticmethod
    def calculate_color_gamut(measurements: dict | None = None) -> dict:
        return {"mock": True, "action": "calculate_color_gamut", "CIE1931": 99.5, "CIE1976": 97.2, "inputs": measurements or {}}

    @staticmethod
    def record_result(label: str, source: str = "") -> dict:
        return {"mock": True, "action": "record_result", "label": label, "source": source}


def execute_plan(plan_path: str, osd_json_path: str, mock: bool = False, output_path: str | None = None) -> list[dict]:
    with open(plan_path, encoding="utf-8") as f:
        plan = json.load(f)

    if mock:
        handlers = _MockHandlers()
    else:
        from agent.modules import AgentActionHandlers

        handlers = AgentActionHandlers(osd_json_path=osd_json_path)

    executor = _build_executor(handlers, mock=mock)
    results = executor.execute(plan)

    if output_path:
        with open(output_path, "w", encoding="utf-8") as f:
            json.dump(results, f, ensure_ascii=False, indent=2)
        print(f"📦 执行结果已保存: {output_path}")

    return results


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Monitor Agent CLI")
    subparsers = parser.add_subparsers(dest="command", required=True)

    run_parser = subparsers.add_parser("llm-run", help="使用 LLM 生成计划并执行")
    run_parser.add_argument("--api-key", default=os.getenv("NVIDIA_API_KEY"), help="NVIDIA API Key，默认读取 NVIDIA_API_KEY")
    run_parser.add_argument("--osd-json", default="demo/excel_json/output_jsons/Main_Menu.json", help="OSD JSON 文件路径")
    run_parser.add_argument("--plan-cache", default="agent/test_plan_cache.json", help="测试计划缓存路径")

    preview_parser = subparsers.add_parser("llm-preview", help="仅使用 LLM 生成计划预览")
    preview_parser.add_argument("--api-key", default=os.getenv("NVIDIA_API_KEY"), help="NVIDIA API Key，默认读取 NVIDIA_API_KEY")
    preview_parser.add_argument("--osd-json", default="demo/excel_json/output_jsons/Main_Menu.json", help="OSD JSON 文件路径")
    preview_parser.add_argument("--output", default="agent/test_plan_preview.json", help="计划输出路径")

    exec_parser = subparsers.add_parser("execute-plan", help="执行本地计划 JSON（无需调用 LLM）")
    exec_parser.add_argument("--plan", default="agent/test_plan_preview.json", help="测试计划 JSON 路径")
    exec_parser.add_argument("--osd-json", default="demo/excel_json/output_jsons/Main_Menu.json", help="OSD JSON 文件路径")
    exec_parser.add_argument("--mock", action="store_true", help="启用 mock 模式（无硬件/GUI 时推荐）")
    exec_parser.add_argument("--output", default="agent/last_execution_results.json", help="执行结果输出路径")

    return parser.parse_args()


def main() -> None:
    args = parse_args()

    if args.command in {"llm-run", "llm-preview"} and not args.api_key:
        raise SystemExit("❌ 缺少 API Key，请通过 --api-key 或 NVIDIA_API_KEY 提供。")

    Path("agent").mkdir(parents=True, exist_ok=True)

    if args.command == "llm-run":
        from agent.color_gamut_test import run

        run(api_key=args.api_key, osd_json_path=args.osd_json, plan_cache_path=args.plan_cache)
    elif args.command == "llm-preview":
        from agent.color_gamut_test import preview_plan

        preview_plan(api_key=args.api_key, osd_json_path=args.osd_json, output_path=args.output)
    elif args.command == "execute-plan":
        execute_plan(plan_path=args.plan, osd_json_path=args.osd_json, mock=args.mock, output_path=args.output)


if __name__ == "__main__":
    main()
