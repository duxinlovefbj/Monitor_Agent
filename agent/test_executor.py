from dataclasses import asdict, is_dataclass
from typing import Callable


class TestExecutor:
    """Generic test plan executor with pluggable action handlers."""

    def __init__(self):
        self._handlers: dict[str, Callable] = {}
        self._results: list[dict] = []

    def register(self, action_type: str, handler: Callable) -> "TestExecutor":
        self._handlers[action_type] = handler
        return self

    def execute(self, plan: dict) -> list[dict]:
        self._results = []
        steps = plan.get("steps", [])
        test_name = plan.get("test_name", "Unnamed Test")

        print(f"\n▶  开始执行: {test_name}  ({len(steps)} 步)\n{'─' * 50}")

        for step in steps:
            step_dict = asdict(step) if is_dataclass(step) else step
            step_id = step_dict.get("id", "?")
            action = step_dict.get("action", "")
            params = step_dict.get("params", {})
            desc = step_dict.get("description", "")

            print(f"[{step_id:>3}] {desc}")
            handler = self._handlers.get(action)
            if handler is None:
                print(f"       ⚠️  未注册的 action: '{action}'，已跳过")
                continue

            try:
                result = handler(**params)
                if result is not None:
                    self._results.append(
                        {
                            "step_id": step_id,
                            "action": action,
                            "description": desc,
                            "result": result,
                        }
                    )
            except TypeError as e:
                print(f"       ❌ 参数错误: {e}")
            except Exception as e:
                print(f"       ❌ 执行异常: {e}")

        print(f"{'─' * 50}\n✅ 执行完毕，共收集 {len(self._results)} 条结果\n")
        return self._results
