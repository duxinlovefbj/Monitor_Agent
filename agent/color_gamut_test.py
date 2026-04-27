"""Color gamut pipeline wired with modular agent handlers."""

import json
import os

from agent.llm_scanner import OSDSemanticScanner
from agent.modules import AgentActionHandlers, build_default_executor
from agent.test_plan_generator import TestPlanGenerator

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


def run(api_key: str, osd_json_path: str, plan_cache_path: str = "test_plan_cache.json"):
    with open(osd_json_path, encoding="utf-8") as f:
        osd_data = json.load(f)

    intent_map = OSDSemanticScanner(api_key).scan_osd_menu(osd_data)
    if not intent_map:
        print("❌ 意图映射失败，终止")
        return

    if os.path.exists(plan_cache_path):
        print(f"📂 加载缓存测试计划: {plan_cache_path}")
        with open(plan_cache_path, encoding="utf-8") as f:
            plan = json.load(f)
    else:
        plan = TestPlanGenerator(api_key).generate(COLOR_GAMUT_SOP, intent_map)
        if not plan:
            print("❌ 测试计划生成失败，终止")
            return
        with open(plan_cache_path, "w", encoding="utf-8") as f:
            json.dump(plan, f, ensure_ascii=False, indent=2)

    handlers = AgentActionHandlers(osd_json_path=osd_json_path)
    executor = build_default_executor(handlers)
    results = executor.execute(plan)

    print("\n📊 测试结果汇总:")
    print(json.dumps(results, ensure_ascii=False, indent=2))


def preview_plan(api_key: str, osd_json_path: str, output_path: str = "test_plan_preview.json"):
    with open(osd_json_path, encoding="utf-8") as f:
        osd_data = json.load(f)

    intent_map = OSDSemanticScanner(api_key).scan_osd_menu(osd_data)
    if not intent_map:
        return

    plan = TestPlanGenerator(api_key).generate(COLOR_GAMUT_SOP, intent_map)
    if not plan:
        return

    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(plan, f, ensure_ascii=False, indent=2)

    print(f"\n📋 测试计划: {plan['test_name']}")
    print(f"{'─' * 50}")
    for step in plan["steps"]:
        print(f"  [{step['id']:>3}] [{step['action']:<22}] {step['description']}")
    print(f"{'─' * 50}")
    print(f"共 {len(plan['steps'])} 步，完整计划已保存至: {output_path}")
