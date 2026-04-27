# color_gamut_test.py
"""
Color Gamut Test — full pipeline.

  OSD JSON ──► OSDSemanticScanner ──► intent_map
                                           │
  SOP text ──► TestPlanGenerator  ──► test_plan   (LLM generates this)
                                           │
               TestExecutor (handlers) ──► results
"""

import json
import os
from llm_scanner import OSDSemanticScanner
from test_plan_generator import TestPlanGenerator
from test_executor import TestExecutor


# ── SOP Text ──────────────────────────────────────────────────────────
# This is the ONLY thing you change when the test procedure changes.
# No code modifications needed anywhere else.
COLOR_GAMUT_SOP = """
Color Gamut 測試步驟：

SDR Mode Test：
1. 將 CA410 探頭定位到螢幕中心（人工操作，請避免探頭擠壓 Panel）
2. OSD 設定：Picture Mode = Standard、Brightness = 100%、Contrast = Default
3. 打開 Screen Test Tool，依序顯示 R / G / B Test Pattern
4. 每個 Pattern 下點擊 CA-S40 軟體的 Measure，記錄色坐標 (x, y)
5. 打開 Color Gamut V1.2 Tool，將 R/G/B (x,y) 值填入並計算 CIE1931、CIE1976

HDR Mode Test：
1. OS 下開啟 HDR
2. OSD Picture Mode 設定為 HDR10
3. 打開 DisplayHDR Tool，依序顯示 R / G / B Test Pattern
4. 每個 Pattern 下點擊 CA-S40 軟體的 Measure，記錄色坐標 (x, y)
5. 計算 CIE1931、CIE1976 色域覆蓋率
"""


# ── Handler Implementations ───────────────────────────────────────────
# These are the only functions tied to real hardware/software interfaces.
# The test logic (sequence, conditions) lives entirely in the LLM-generated plan.

def handle_navigate_osd(path: list, value=None):
    """Stub: replace with your actual OSD navigation driver call."""
    print(f"       → OSD navigate: {' > '.join(path)}" + (f" = {value}" if value is not None else ""))
    # e.g. osd_driver.navigate(path, value)


def handle_show_test_pattern(pattern: str):
    """Stub: replace with your unified test pattern interface."""
    print(f"       → Show pattern: {pattern}")
    # e.g. screen_tool.show_pattern(pattern)


def handle_measure_ca410(label: str = ""):
    """Stub: replace with your CA410 / CA-S40 SDK call."""
    print(f"       → CA410 measuring... [{label}]")
    # result = ca410.measure()
    # return {"x": result.x, "y": result.y}
    return {"x": 0.640, "y": 0.330}  # placeholder


def handle_enable_hdr(enabled: bool, mode: str = ""):
    """Stub: replace with your OS HDR toggle."""
    state = "ON" if enabled else "OFF"
    print(f"       → HDR {state}" + (f" mode={mode}" if mode else ""))
    # e.g. os_hdr.set(enabled)


def handle_wait_human(instruction: str):
    """Pause and wait for operator confirmation."""
    print(f"\n       👤 人工操作: {instruction}")
    input("       按 Enter 继续...")


def handle_calculate_color_gamut(measurements: dict = None):
    """Stub: replace with your Color Gamut V1.2 calculation logic."""
    print(f"       → 计算色域覆盖率 (CIE1931 / CIE1976)")
    # return color_gamut_tool.calculate(measurements)
    return {"CIE1931": 99.5, "CIE1976": 97.2}  # placeholder


def handle_record_result(label: str, source: str = ""):
    """Stub: write result to your report/database."""
    print(f"       → 记录结果: {label}")


# ── Main Pipeline ─────────────────────────────────────────────────────

def run(api_key: str, osd_json_path: str, plan_cache_path: str = "test_plan_cache.json"):
    # 1. Load OSD JSON
    with open(osd_json_path, encoding="utf-8") as f:
        osd_data = json.load(f)

    # 2. Semantic scan — find menu paths
    scanner = OSDSemanticScanner(api_key)
    intent_map = scanner.scan_osd_menu(osd_data)
    if not intent_map:
        print("❌ 意图映射失败，终止")
        return

    # 3. Generate test plan from SOP (or load cached plan)
    if os.path.exists(plan_cache_path):
        print(f"📂 加载缓存测试计划: {plan_cache_path}")
        with open(plan_cache_path, encoding="utf-8") as f:
            plan = json.load(f)
    else:
        generator = TestPlanGenerator(api_key)
        plan = generator.generate(COLOR_GAMUT_SOP, intent_map)
        if not plan:
            print("❌ 测试计划生成失败，终止")
            return
        with open(plan_cache_path, "w", encoding="utf-8") as f:
            json.dump(plan, f, ensure_ascii=False, indent=2)
        print(f"💾 测试计划已缓存至: {plan_cache_path}")

    # 4. Wire up executor with handlers
    executor = (TestExecutor()
        .register("navigate_osd",        handle_navigate_osd)
        .register("show_test_pattern",    handle_show_test_pattern)
        .register("measure_ca410",        handle_measure_ca410)
        .register("enable_hdr",           handle_enable_hdr)
        .register("wait_human",           handle_wait_human)
        .register("calculate_color_gamut",handle_calculate_color_gamut)
        .register("record_result",        handle_record_result))

    # 5. Execute
    results = executor.execute(plan)

    print("\n📊 测试结果汇总:")
    print(json.dumps(results, ensure_ascii=False, indent=2))

# 在 color_gamut_test.py 里加这个函数
def preview_plan(api_key: str, osd_json_path: str, output_path: str = "test_plan_preview.json"):
    """只生成测试计划并输出，不执行任何操作。"""
    with open(osd_json_path, encoding="utf-8") as f:
        osd_data = json.load(f)

    intent_map = OSDSemanticScanner(api_key).scan_osd_menu(osd_data)
    if not intent_map:
        return

    plan = TestPlanGenerator(api_key).generate(COLOR_GAMUT_SOP, intent_map)
    if not plan:
        return

    # 保存到文件
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(plan, f, ensure_ascii=False, indent=2)

    # 终端打印可读摘要
    print(f"\n📋 测试计划: {plan['test_name']}")
    print(f"{'─' * 50}")
    for step in plan["steps"]:
        print(f"  [{step['id']:>3}] [{step['action']:<22}] {step['description']}")
    print(f"{'─' * 50}")
    print(f"共 {len(plan['steps'])} 步，完整计划已保存至: {output_path}")


if __name__ == "__main__":
    API_KEY = "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"
    OSD_JSON = r"C:\Users\Administrator\PycharmProjects\Monitor_Agent\demo\excel_json\output_jsons\Main_Menu.json"

    preview_plan(API_KEY, OSD_JSON)  # 只看计划
    # run(API_KEY, OSD_JSON)          # 确认无误后再执行

