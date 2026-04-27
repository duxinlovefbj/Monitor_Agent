# test_plan_generator.py
import json
import requests


class TestPlanGenerator:
    """
    Converts a SOP description + OSD intent map into a fully executable test plan.
    When the SOP changes, just update the text — no code modifications needed.
    """

    AVAILABLE_ACTIONS = {
        "navigate_osd": "Navigate OSD menu to the given path; optionally set a numeric value",
        "show_test_pattern": "Display a test pattern on screen (R / G / B / White / Black / Gray)",
        "press_key": "Send physical OSD key action (上键/下键/左键/右键/中键, short/long)",
        "measure_ca410": "Trigger CA410 colorimeter measurement, returns xy chromaticity coordinates",
        "enable_hdr": "Enable or disable OS-level HDR mode",
        "wait_human": "Pause execution and display an instruction for the operator",
        "calculate_color_gamut": "Calculate CIE1931/CIE1976 color gamut from collected R/G/B measurements",
        "record_result": "Persist a labeled result entry into the test report",
    }

    def __init__(self, api_key: str):
        self.invoke_url = "https://integrate.api.nvidia.com/v1/chat/completions"
        self.headers = {
            "Authorization": f"Bearer {api_key}",
            "Accept": "application/json",
        }
        self.model = "qwen/qwen3.5-122b-a10b"

    def _build_prompt(self, sop_text: str, intent_map: dict) -> str:
        actions_desc = "\n".join(
            f'  - "{k}": {v}' for k, v in self.AVAILABLE_ACTIONS.items()
        )
        return f"""你是测试自动化工程师。根据以下信息生成完整的可执行测试计划。

【可用动作类型】
{actions_desc}

【OSD 意图映射（菜单路径）】
{json.dumps(intent_map, ensure_ascii=False, indent=2)}

【测试 SOP】
{sop_text}

【规则】
1. 只输出合法 JSON，不含任何 Markdown 标记或解释文字。
2. 探头定位等人工步骤使用 wait_human action。
3. 软件画面（test pattern）使用 show_test_pattern action。
4. OSD 操作使用 navigate_osd，path 必须来自意图映射中的路径。
5. 每个步骤必须包含 description 字段。
6. HDR 模式切换使用 enable_hdr action。
7. 测量后使用 record_result 保存结果。

【输出格式】
{{
  "test_name": "...",
  "steps": [
    {{
      "id": 1,
      "action": "action_type",
      "params": {{}},
      "description": "..."
    }}
  ]
}}"""

    def generate(self, sop_text: str, intent_map: dict) -> dict | None:
        """
        Generate a structured test plan from a SOP and OSD intent map.
        Returns a dict with 'test_name' and 'steps', or None on failure.
        """
        print("🧠 正在生成测试计划，请稍候...")

        payload = {
            "model": self.model,
            "messages": [{"role": "user", "content": self._build_prompt(sop_text, intent_map)}],
            "max_tokens": 8192,
            "temperature": 0.1,
            "top_p": 0.95,
            "stream": False,
        }

        try:
            resp = requests.post(self.invoke_url, headers=self.headers, json=payload)
            resp.raise_for_status()

            content = resp.json()["choices"][0]["message"]["content"]
            if not content:
                print("❌ API 返回空内容")
                return None

            cleaned = content.replace("```json", "").replace("```", "").strip()
            plan = json.loads(cleaned)
            print(f"✅ 测试计划生成完成，共 {len(plan.get('steps', []))} 步")
            return plan

        except requests.exceptions.RequestException as e:
            print(f"❌ 网络请求失败: {e}")
        except json.JSONDecodeError as e:
            print(f"❌ JSON 解析失败: {e}\n原始输出:\n{content}")
        except Exception as e:
            print(f"❌ 未知错误: {e}")

        return None
