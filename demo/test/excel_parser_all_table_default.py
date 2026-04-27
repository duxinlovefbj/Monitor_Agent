import pandas as pd
import json
import os
import re
import copy


def safe_convert_value(val):
    """安全地将数字转换为int/float，保持JSON整洁"""
    if isinstance(val, (int, float)): return val
    val_str = str(val).strip()
    try:
        return float(val_str) if '.' in val_str else int(val_str)
    except ValueError:
        return val_str


def parse_sparse_tree(records: list, level_cols: list) -> dict:
    """带状态继承的树形解析器（处理 Quick Switch 继承 Range 的问题）"""
    tree = {}
    current_path = [None] * len(level_cols)
    last_parent_path = []
    last_range = None

    for row in records:
        first_valid_idx = -1
        for i, col_name in enumerate(level_cols):
            val = row.get(col_name)
            if pd.notna(val) and str(val).strip() != "":
                first_valid_idx = i
                break

        if first_valid_idx == -1: continue

        for i in range(first_valid_idx, len(level_cols)):
            current_path[i] = None

        for i in range(first_valid_idx, len(level_cols)):
            val = row.get(level_cols[i])
            if pd.notna(val) and str(val).strip() != "":
                current_path[i] = str(val).strip()

        current_node = tree
        valid_path = []
        for i in range(len(level_cols)):
            node_name = current_path[i]
            if node_name is None: break
            valid_path.append(node_name)
            if node_name not in current_node:
                current_node[node_name] = {}
            current_node = current_node[node_name]

        # ======= 处理 Default 与 Range 的智能挂载 =======
        default_val = row.get('Default')
        raw_range_val = row.get('Range')

        current_parent_path = valid_path[:-1]
        range_val = None

        # Range继承逻辑
        if pd.notna(raw_range_val) and str(raw_range_val).strip() != "":
            range_val = str(raw_range_val).strip()
            last_range = range_val
            last_parent_path = current_parent_path
        else:
            if current_parent_path == last_parent_path and last_range is not None:
                range_val = last_range
            else:
                last_range = None

        setting_path = valid_path.copy()
        if pd.isna(range_val) or str(range_val).strip() == "":
            if len(setting_path) > 1:
                setting_path.pop()

        target_node = tree
        for p in setting_path:
            target_node = target_node[p]

        if pd.notna(default_val) and str(default_val).strip() != "":
            target_node["Default"] = safe_convert_value(default_val)

        if range_val:
            target_node["__Range__"] = range_val

    return tree


def resolve_tree_references(tree, all_sheets_dict):
    """跨表合并链接器"""
    if not isinstance(tree, dict): return tree
    new_tree = {}
    for key, value in tree.items():
        if "Reference" in str(key):
            match = re.search(r'Reference\s+(.*)', str(key))
            if match:
                ref_sheet_name = match.group(1).strip()
                target_sheet = next((s for s in all_sheets_dict.keys() if ref_sheet_name.lower() in s.lower()), None)
                if target_sheet:
                    return resolve_tree_references(all_sheets_dict[target_sheet], all_sheets_dict)

        if key in ["Default", "__Range__"]:
            new_tree[key] = value
        else:
            new_tree[key] = resolve_tree_references(value, all_sheets_dict)
    return new_tree


def load_picture_mode_defaults(file_path: str) -> dict:
    """鲁棒性极强的 Picture Mode 解析器，无视空表头"""
    try:
        excel_file = pd.ExcelFile(file_path)
        target_sheet = next((s for s in excel_file.sheet_names if "picture mode" in s.lower()), None)
        if not target_sheet:
            print("    [-] 未找到包含 'Picture Mode' 的工作表")
            return {}

        df = pd.read_excel(file_path, sheet_name=target_sheet, header=None)
        header_idx = -1
        # 寻找包含 Standard 和 Gam 的那一行作为基准行
        for idx, row in df.iterrows():
            vals = [str(v).strip().lower() for v in row.values if pd.notna(v)]
            if 'standard' in vals and 'game' in vals:
                header_idx = idx
                break

        if header_idx == -1: return {}

        df = pd.read_excel(file_path, sheet_name=target_sheet, header=header_idx)

        # 提取真实的模式名称 (过滤掉NaN或无用列)
        mode_cols = [c for c in df.columns[1:] if pd.notna(c) and "unnamed" not in str(c).lower()]

        mode_defaults = {}
        for col in mode_cols:
            mode_defaults[str(col).strip()] = {}

        # 使用 iloc[0] 强制读取第一列作为设置名称，避开表头为空导致的 bug
        for idx, row in df.iterrows():
            setting_name = str(row.iloc[0]).strip()
            if setting_name in ["", "nan", "None"]: continue
            for col in mode_cols:
                val = row[col]
                if pd.notna(val):
                    clean_setting = setting_name.replace("(HUE)", "").strip()
                    mode_defaults[str(col).strip()][clean_setting] = safe_convert_value(val)

        print(f"    [+] 成功提取 Picture Mode 预设: {list(mode_defaults.keys())}")
        return mode_defaults
    except Exception as e:
        print(f"    [-] Picture Mode 解析失败: {e}")
        return {}


def apply_custom_business_rules(tree: dict, mode_defaults: dict) -> dict:
    if not isinstance(tree, dict): return tree

    def split_newline_keys(node):
        if not isinstance(node, dict): return
        keys_to_split = [k for k in list(node.keys()) if isinstance(k, str) and '\n' in k]
        for k in keys_to_split:
            val = node.pop(k)
            parts = [p.strip() for p in k.split('\n') if p.strip()]
            for part in parts:
                node[part] = copy.deepcopy(val)
        for k, v in node.items():
            if not str(k).startswith("__") and k != "Default":
                split_newline_keys(v)

    def parse_newline_ranges(node):
        if not isinstance(node, dict): return
        if "__Range__" in node:
            range_str = str(node["__Range__"])
            if '\n' in range_str:
                options = [o.strip() for o in range_str.split('\n') if o.strip()]
                for opt in options:
                    if opt not in node:
                        node[opt] = {}
        for k, v in node.items():
            if not str(k).startswith("__") and k != "Default":
                parse_newline_ranges(v)

    def propagate_picture_settings(node):
        global_settings = {}

        # A. 升级索引库：除了收集节点，还要把路径（Path）记录下来
        def collect_settings(n, current_path=[]):
            if not isinstance(n, dict): return
            for k, v in n.items():
                if isinstance(v, dict):
                    if k not in global_settings:
                        global_settings[k] = {"node": v, "path": current_path}
                    collect_settings(v, current_path + [k])

        collect_settings(node, ["Root"])

        def find_picture_node(n):
            if not isinstance(n, dict): return None
            if "Picture" in n and isinstance(n["Picture"], dict) and "Standard" in n["Picture"]:
                return n["Picture"]
            for v in n.values():
                res = find_picture_node(v)
                if res: return res
            return None

        pic_node = find_picture_node(node)
        if not pic_node: return

        shared_settings = {}
        for mode_name, mode_contents in pic_node.items():
            # 排除带下划线的临时标记和 Default
            if isinstance(mode_contents, dict) and len(
                    [k for k in mode_contents.keys() if not k.startswith("__") and k != "Default"]) > 1:
                for k, v in mode_contents.items():
                    if not str(k).startswith("__") and k != "Default":
                        shared_settings[k] = copy.deepcopy(v)
                        if "Default" in shared_settings[k]:
                            del shared_settings[k]["Default"]

        for mode_name, mode_contents in pic_node.items():
            if not isinstance(mode_contents, dict) or mode_name in ["Default", "__Range__"]: continue

            # 铺设本模块原生参数 (这些不会被打上 External 标记)
            for sk, sv in shared_settings.items():
                if sk not in mode_contents:
                    mode_contents[sk] = copy.deepcopy(sv)

            # 注入 Excel 预设
            if mode_defaults and mode_name in mode_defaults:
                for setting_name, def_val in mode_defaults[mode_name].items():
                    if setting_name not in mode_contents:
                        if setting_name in global_settings:
                            mode_contents[setting_name] = copy.deepcopy(global_settings[setting_name]["node"])
                            if "Default" in mode_contents[setting_name]:
                                del mode_contents[setting_name]["Default"]

                            # ==========================================
                            # 【核心改进】：打上外部链接标记与溯源路径
                            # ==========================================
                            # 清洗掉一些冗长的根节点名字，保持路径整洁
                            clean_path = [p for p in global_settings[setting_name]["path"] if
                                          p not in ["Root", "Main Menu", "Settings"]]
                            source_path = " -> ".join(clean_path + [setting_name])

                            mode_contents[setting_name]["__Is_External_Link__"] = True
                            mode_contents[setting_name]["__Source_Path__"] = source_path
                        else:
                            mode_contents[setting_name] = {
                                "__Is_External_Link__": True,
                                "__Source_Path__": "Unknown"
                            }
                    mode_contents[setting_name]["Default"] = def_val

    def resolve_global_picture_references(node):
        if not isinstance(node, dict): return
        for key, child in node.items():
            if isinstance(child, dict) and "Default" in child:
                def_str = str(child["Default"])
                if "參考" in def_str and "Picture" in def_str:
                    setting_name = key
                    global_def = {}
                    if mode_defaults:
                        sample_mode = list(mode_defaults.keys())[0]
                        matched_setting = next(
                            (sn for sn in mode_defaults[sample_mode].keys() if setting_name.lower() in sn.lower()),
                            None)
                        if matched_setting:
                            for mode, settings in mode_defaults.items():
                                if matched_setting in settings:
                                    global_def[mode] = settings[matched_setting]
                    if global_def:
                        child["Default"] = global_def
                    else:
                        del child["Default"]
            resolve_global_picture_references(child)

    def clean_range_keys(node):
        if not isinstance(node, dict): return
        if "__Range__" in node:
            del node["__Range__"]
        for v in node.values():
            clean_range_keys(v)

    split_newline_keys(tree)
    parse_newline_ranges(tree)
    propagate_picture_settings(tree)
    resolve_global_picture_references(tree)
    clean_range_keys(tree)

    return tree


def build_super_menu(file_path: str, root_sheet: str, output_json: str = None):
    if not os.path.exists(file_path):
        print(f"[-] 文件不存在: {file_path}")
        return

    print(f"[*] 正在加载 Excel 并初始化全表索引...")
    excel_file = pd.ExcelFile(file_path)
    all_sheets_data = {}
    possible_cols = ['Main Menu', 'Sub Menu\n Level 1', 'Sub Menu\n Level 2', 'Sub Menu\n Level 3',
                     'Sub Menu\nLevel 3+']

    for sheet_name in excel_file.sheet_names:
        try:
            df_raw = pd.read_excel(file_path, sheet_name=sheet_name, header=None, nrows=15)
        except Exception:
            continue

        header_idx = -1
        for idx, row in df_raw.iterrows():
            if 'Main Menu' in [str(val).strip() for val in row.values]:
                header_idx = idx
                break

        if header_idx == -1: continue

        df = pd.read_excel(file_path, sheet_name=sheet_name, header=header_idx)
        actual_cols = [c for c in possible_cols if c in df.columns]
        if not actual_cols: continue

        target_cols = actual_cols.copy()
        if 'Range' in df.columns: target_cols.append('Range')
        if 'Default' in df.columns: target_cols.append('Default')

        records = df[target_cols].to_dict('records')
        all_sheets_data[sheet_name] = parse_sparse_tree(records, actual_cols)
        print(f"    + 已解析: '{sheet_name}'")

    if root_sheet not in all_sheets_data:
        print(f"[-] 错误: 根工作表 '{root_sheet}' 未找到。")
        return

    print(f"[*] 正在提取 Picture Mode 预设映射...")
    mode_defaults = load_picture_mode_defaults(file_path)

    print(f"[*] 正在执行跨表组装 (Stitching)...")
    super_tree = resolve_tree_references(all_sheets_data[root_sheet], all_sheets_data)

    print(f"[*] 正在应用复杂业务规则注入...")
    final_tree = apply_custom_business_rules(super_tree, mode_defaults)

    json_output = json.dumps(final_tree, ensure_ascii=False, indent=4)
    if output_json:
        with open(output_json, 'w', encoding='utf-8') as f:
            f.write(json_output)
        print(f"[+] 超级菜单树已生成，保存至: {output_json}")

    return final_tree


if __name__ == "__main__":
    # 配置你的路径
    FILE_PATH = r"C:\Users\Administrator\Desktop\test_clearn_osd_tree.xlsx"
    ROOT_SHEET = "First Layer"
    OUTPUT_FILE = "../super_menu_tree.json"

    build_super_menu(FILE_PATH, ROOT_SHEET, OUTPUT_FILE)