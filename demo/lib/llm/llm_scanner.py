import json
import requests


class OSDSemanticScanner:
    def __init__(self, api_key):
        self.invoke_url = "https://integrate.api.nvidia.com/v1/chat/completions"
        self.headers = {
            "Authorization": f"Bearer {api_key}",
            "Accept": "application/json"
        }
        # 使用 Qwen 3.5 122B，逻辑推理能力极强
        self.model = "qwen/qwen3.5-122b-a10b"

    def _build_system_prompt(self):
        """构建强制 JSON 输出的系统指令"""
        # 2. 对于列表类的功能（如图像模式、色温、Gamma），请返回父级菜单的路径，不要具体到某个选项（例如返回 ["Picture ( SDR 時)", "Gamma"]）。
        return """你是一个专业的显示器 OSD 菜单解析引擎。我会给你一份 OSD 菜单的 JSON 结构。你的任务是找到 8 个核心测试功能的完整路径。

规则：
1. 必须返回包含从根节点到目标节点名称的严格数组格式（例如 ["Main Menu(Setting)", "Picture ( SDR 時)", "Brightness"]）。
2. 如果某个功能在该 JSON 中不存在，请将值设为 null。
3. 必须只输出合法的 JSON 格式，绝对不要包含任何额外的解释文本、开场白或 Markdown 标记（如 ```json ）。
4. 部分功能可能命名有不同：如 "RESET_ALL" 可能显示为 "Reset to default"

预期输出结构：
{
  "INTENT_BRIGHTNESS": [],
  "INTENT_CONTRAST": [],
  "INTENT_PICTURE_MODE_STANDARD": [],
  "INTENT_PICTURE_MODE_SRGB": [],
  "INTENT_COLOR_TEMP_COOL": [],
  "INTENT_COLOR_TEMP_NATURAL": [],
  "INTENT_COLOR_TEMP_NORMAL": [],
  "INTENT_COLOR_TEMP_WARM": [],
  "INTENT_GAMMA_OFF": [],
  "INTENT_GAMMA_1.8": [],
  "INTENT_GAMMA_2.0": [],
  "INTENT_GAMMA_2.2": [],
  "INTENT_GAMMA_2.4": [],
  "INTENT_GAMMA_2.6": [],
  "INTENT_RESET_ALL": [],
  "INTENT_INPUT_SOURCE": []
}"""

    def scan_osd_menu(self, osd_json_data):
        """
        扫描 OSD JSON 数据并返回意图映射字典
        """
        print("🚀 正在调用 NVIDIA API (Qwen-122B) 进行 OSD 语义解析，请稍候...")

        json_str = json.dumps(osd_json_data, ensure_ascii=False)

        payload = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": self._build_system_prompt()},
                {"role": "user", "content": f"请解析以下 OSD JSON，并严格遵守返回格式:\n{json_str}"}
            ],
            "max_tokens": 4096,
            "temperature": 0.1,
            "top_p": 0.95,
            "stream": False
            # 🚨 已经移除 "chat_template_kwargs": {"enable_thinking": True}，防止非推理模型报错
        }

        try:
            response = requests.post(self.invoke_url, headers=self.headers, json=payload)
            response.raise_for_status()

            result_data = response.json()

            # 安全提取 message 节点
            message = result_data.get("choices", [{}])[0].get("message", {})
            content = message.get("content")

            # 🚨 新增拦截：如果 API 返回了 None
            if content is None:
                print("❌ API 返回的 content 为空！大模型可能触发了安全拦截或遇到了内部错误。")
                print("👉 完整的 API 原始返回包如下：")
                print(json.dumps(result_data, indent=4, ensure_ascii=False))
                return None

            # Agent 清洗层：暴力去除潜在的 Markdown 代码块残留
            cleaned_content = content.replace("```json", "").replace("```", "").strip()

            # 转化为 Python 字典
            mapping_dict = json.loads(cleaned_content)
            print("✅ 语义解析完成！")
            return mapping_dict

        except requests.exceptions.RequestException as e:
            print(f"❌ API 网络请求失败: {e}")
            return None
        except json.JSONDecodeError as e:
            print(f"❌ LLM 返回的 JSON 格式解析失败: {e}")
            # 如果 content 有值才打印，否则避免再次报错
            if 'content' in locals() and content:
                print(f"大模型原始输出内容如下:\n{content}")
            return None
        except KeyError as e:
            print(f"❌ 提取数据失败，API 返回结构可能已改变: {e}\nAPI 完整响应: {result_data}")
            return None


# ==========================================
# 测试模块 (可直接运行验证)
# ==========================================
if __name__ == "__main__":
    import os

    # 替换为你自己的 KEY
    API_KEY = "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"
    scanner = OSDSemanticScanner(API_KEY)

    # 读取你项目里的 JSON 文件进行测试
    test_json_path = r"C:\Users\Administrator\PycharmProjects\Monitor_Agent\demo\excel_json\output_jsons\Main_Menu.json"  # 这里换成你的 JSON 文件名
    if os.path.exists(test_json_path):
        with open(test_json_path, 'r', encoding='utf-8') as f:
            raw_osd_data = json.load(f)

        mapping_result = scanner.scan_osd_menu(raw_osd_data)

        if mapping_result:
            print("\n🎉 成功提取出意图映射表：")
            print(json.dumps(mapping_result, indent=4, ensure_ascii=False))
    else:
        print("未找到测试 JSON 文件。")