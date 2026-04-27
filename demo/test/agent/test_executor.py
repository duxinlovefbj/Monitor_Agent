# test_executor.py
from typing import Callable


class TestExecutor:
    """
    Generic test plan executor.

    Register a handler for each action type once.
    When the SOP changes and the LLM generates new action sequences,
    the executor runs them without any code modifications.

    Usage:
        executor = (TestExecutor()
            .register("navigate_osd", my_osd_handler)
            .register("measure_ca410", my_measure_handler))
        results = executor.execute(plan)
    """

    def __init__(self):
        self._handlers: dict[str, Callable] = {}
        self._results: list[dict] = []

    def register(self, action_type: str, handler: Callable) -> "TestExecutor":
        """Register a callable for an action type. Supports method chaining."""
        self._handlers[action_type] = handler
        return self

    def execute(self, plan: dict) -> list[dict]:
        """
        Execute all steps sequentially.
        Returns result entries from steps that produced output.
        """
        self._results = []
        steps = plan.get("steps", [])
        test_name = plan.get("test_name", "Unnamed Test")

        print(f"\n▶  开始执行: {test_name}  ({len(steps)} 步)\n{'─' * 50}")

        for step in steps:
            step_id = step.get("id", "?")
            action = step.get("action", "")
            params = step.get("params", {})
            desc = step.get("description", "")

            print(f"[{step_id:>3}] {desc}")

            handler = self._handlers.get(action)
            if handler is None:
                print(f"       ⚠️  未注册的 action: '{action}'，已跳过")
                continue

            try:
                result = handler(**params)
                if result is not None:
                    self._results.append({
                        "step_id": step_id,
                        "action": action,
                        "description": desc,
                        "result": result,
                    })
            except TypeError as e:
                print(f"       ❌ 参数错误: {e}")
            except Exception as e:
                print(f"       ❌ 执行异常: {e}")

        print(f"{'─' * 50}\n✅ 执行完毕，共收集 {len(self._results)} 条结果\n")
        return self._results
