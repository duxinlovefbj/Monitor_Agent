# Agent 目录运行说明

本目录提供了一个基于 LLM 的显示器测试 Agent，包含：
- OSD 菜单语义解析（`llm_scanner.py`）
- 测试计划生成（`test_plan_generator.py`）
- 测试计划执行器（`test_executor.py` + `modules/`）

## 1. 直接运行现状

`agent` 目录原始代码主要是函数入口（例如 `color_gamut_test.run(...)`），没有完整的 CLI 主程序。
另外，默认执行流程依赖：
- 外部 LLM API（NVIDIA integrate API）
- 实际硬件/工具（CA410、OSD 按键控制、图案显示）

因此在普通开发环境中通常**无法直接一条命令完整跑通**。

## 2. 新增调用程序

已新增 `agent/run_agent.py`，提供统一 CLI，支持三种模式：

1) `llm-run`：调用 LLM 生成计划后执行。
2) `llm-preview`：仅生成计划，不执行。
3) `execute-plan`：执行本地计划 JSON；支持 `--mock`，可在无硬件环境下运行。

## 3. 环境准备

建议 Python 3.10+。

安装依赖（最小集合）：

```bash
pip install requests cryptography
```

> 若要真实执行硬件动作，还需满足 `demo/lib` 中对应驱动、工具和运行环境要求。

## 4. 使用方式

默认工作目录为仓库根目录 `/workspace/Monitor_Agent`。

### 4.1 仅查看帮助

```bash
python -m agent.run_agent --help
python -m agent.run_agent llm-run --help
python -m agent.run_agent execute-plan --help
```

### 4.2 LLM 生成 + 执行（需要 API Key）

```bash
export NVIDIA_API_KEY="<your_api_key>"
python -m agent.run_agent llm-run \
  --osd-json demo/excel_json/output_jsons/Main_Menu.json \
  --plan-cache agent/test_plan_cache.json
```

### 4.3 仅生成计划预览（需要 API Key）

```bash
export NVIDIA_API_KEY="<your_api_key>"
python -m agent.run_agent llm-preview \
  --osd-json demo/excel_json/output_jsons/Main_Menu.json \
  --output agent/test_plan_preview.json
```

### 4.4 无法直接运行时：本地计划 + Mock 执行（推荐）

不依赖 LLM、不依赖硬件设备：

```bash
python -m agent.run_agent execute-plan \
  --plan agent/test_plan_preview.json \
  --osd-json demo/excel_json/output_jsons/Main_Menu.json \
  --mock \
  --output agent/last_execution_results.json
```

## 5. 常见问题

### Q1: 报错缺少 API Key
请传入 `--api-key` 或设置 `NVIDIA_API_KEY`。

### Q2: 有计划但执行报参数不匹配
`run_agent.py` 已对常见字段做了兼容转换（例如 `value -> set_value`、`state -> enabled`）。

### Q3: 在 Linux/CI 环境无法操作真实设备
使用 `execute-plan --mock`，可验证流程编排和结果落盘。
