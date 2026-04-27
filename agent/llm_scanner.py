import json
import os
import requests
import sqlite3
from cryptography.fernet import Fernet


class KeyManager:
    def __init__(self, db_path="config.db", key_file="master.key"):
        self.db_path = db_path
        self.key_file = key_file
        self._init_master_key()
        self._init_db()

    def _init_master_key(self):
        if not os.path.exists(self.key_file):
            key = Fernet.generate_key()
            with open(self.key_file, "wb") as f:
                f.write(key)
        with open(self.key_file, "rb") as f:
            self.cipher_suite = Fernet(f.read())

    def _init_db(self):
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS api_config (
                    service_name TEXT PRIMARY KEY,
                    encrypted_key BLOB
                )
                """
            )
            conn.commit()

    def save_key(self, service_name, raw_key):
        encrypted_key = self.cipher_suite.encrypt(raw_key.encode("utf-8"))
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                "INSERT OR REPLACE INTO api_config (service_name, encrypted_key) VALUES (?, ?)",
                (service_name, encrypted_key),
            )
            conn.commit()

    def load_key(self, service_name):
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.execute(
                "SELECT encrypted_key FROM api_config WHERE service_name = ?",
                (service_name,),
            )
            row = cursor.fetchone()
        if row:
            return self.cipher_suite.decrypt(row[0]).decode("utf-8")
        return None


class OSDSemanticScanner:
    def __init__(self, api_key):
        self.invoke_url = "https://integrate.api.nvidia.com/v1/chat/completions"
        self.headers = {"Authorization": f"Bearer {api_key}", "Accept": "application/json"}
        self.model = "qwen/qwen3.5-122b-a10b"

    def _build_system_prompt(self):
        return """你是一个专业的显示器 OSD 菜单解析引擎。我会给你一份 OSD 菜单的 JSON 结构。你的任务是找到 8 个核心测试功能的完整路径。

规则：
1. 必须返回包含从根节点到目标节点名称的严格数组格式（例如 [\"Main Menu(Setting)\", \"Picture ( SDR 時)\", \"Brightness\"]）。
2. 如果某个功能在该 JSON 中不存在，请将值设为 null。
3. 必须只输出合法的 JSON 格式，绝对不要包含任何额外的解释文本、开场白或 Markdown 标记（如 ```json ）。
4. 部分功能可能命名有不同：如 \"RESET_ALL\" 可能显示为 \"Reset to default\"

预期输出结构：
{
  \"INTENT_BRIGHTNESS\": [],
  \"INTENT_CONTRAST\": [],
  \"INTENT_PICTURE_MODE_STANDARD\": [],
  \"INTENT_PICTURE_MODE_SRGB\": [],
  \"INTENT_COLOR_TEMP_COOL\": [],
  \"INTENT_COLOR_TEMP_NATURAL\": [],
  \"INTENT_COLOR_TEMP_NORMAL\": [],
  \"INTENT_COLOR_TEMP_WARM\": [],
  \"INTENT_GAMMA_OFF\": [],
  \"INTENT_GAMMA_1.8\": [],
  \"INTENT_GAMMA_2.0\": [],
  \"INTENT_GAMMA_2.2\": [],
  \"INTENT_GAMMA_2.4\": [],
  \"INTENT_GAMMA_2.6\": [],
  \"INTENT_RESET_ALL\": [],
  \"INTENT_INPUT_SOURCE\": []
}"""

    def scan_osd_menu(self, osd_json_data):
        json_str = json.dumps(osd_json_data, ensure_ascii=False)
        payload = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": self._build_system_prompt()},
                {"role": "user", "content": f"请解析以下 OSD JSON，并严格遵守返回格式:\n{json_str}"},
            ],
            "max_tokens": 4096,
            "temperature": 0.1,
            "top_p": 0.95,
            "stream": False,
        }

        try:
            response = requests.post(self.invoke_url, headers=self.headers, json=payload)
            response.raise_for_status()
            result_data = response.json()
            content = result_data.get("choices", [{}])[0].get("message", {}).get("content")
            if content is None:
                return None
            cleaned = content.replace("```json", "").replace("```", "").strip()
            return json.loads(cleaned)
        except Exception:
            return None
