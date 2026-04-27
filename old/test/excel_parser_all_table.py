import copy
import pandas as pd
import json
import os
import re


def parse_sparse_tree(data_rows: list, level_cols_count: int) -> dict:
    tree = {}
    current_path = [None] * level_cols_count

    for row in data_rows:
        first_valid_idx = -1
        for i in range(level_cols_count):
            val = row[i]
            if pd.notna(val) and str(val).strip() != "":
                first_valid_idx = i
                break

        if first_valid_idx == -1:
            continue

        for i in range(first_valid_idx, level_cols_count):
            current_path[i] = None

        for i in range(first_valid_idx, level_cols_count):
            val = row[i]
            if pd.notna(val) and str(val).strip() != "":
                current_path[i] = str(val).strip()

        current_node = tree
        for i in range(level_cols_count):
            node_name = current_path[i]
            if node_name is None:
                break
            if node_name not in current_node:
                current_node[node_name] = {}
            current_node = current_node[node_name]

    return tree


def resolve_tree_references(tree, all_sheets_dict):
    if not isinstance(tree, dict):
        return tree

    new_tree = {}
    for key, value in tree.items():
        if "Reference" in key:
            match = re.search(r'Reference\s+(.*)', key)
            if match:
                ref_sheet_name = match.group(1).strip()
                # 兼容处理：有时 Excel 里的 Reference 名称末尾会有多余空格或换行
                # 我们遍历字典，做忽略大小写和首尾空格的模糊匹配
                target_sheet = None
                for sheet_name in all_sheets_dict.keys():
                    if ref_sheet_name.lower() in sheet_name.lower():
                        target_sheet = sheet_name
                        break

                if target_sheet:
                    ref_sub_tree = all_sheets_dict[target_sheet]
                    return resolve_tree_references(ref_sub_tree, all_sheets_dict)
                else:
                    print(f"    [警告] 找不到引用指向的工作表: '{ref_sheet_name}'")

        new_tree[key] = resolve_tree_references(value, all_sheets_dict)

    return new_tree


def apply_custom_business_rules(tree: dict) -> dict:
    """
    业务规则后处理器：专门处理特定的显示器菜单逻辑
    """
    if not isinstance(tree, dict):
        return tree

    # ==========================================
    # 规则 2: 递归处理包含换行符 "\n" 的键 (拆分语言菜单)
    # ==========================================
    def split_newline_keys(node):
        if not isinstance(node, dict):
            return

        # 找出当前层级所有名字里带 \n 的键
        keys_to_split = [k for k in list(node.keys()) if '\n' in k]
        for k in keys_to_split:
            val = node.pop(k)  # 移除旧的合并键并获取它的值
            # 按换行符拆分，并去除首尾空格，过滤掉空字符串
            parts = [p.strip() for p in k.split('\n') if p.strip()]
            for part in parts:
                node[part] = copy.deepcopy(val)  # 将拆分后的名字作为独立的新键

        # 递归检查子节点
        for v in node.values():
            split_newline_keys(v)

    # ==========================================
    # 规则 1: 图像模式 (Picture) 子菜单共享扩散
    # ==========================================
    def propagate_picture_settings(node):
        if not isinstance(node, dict):
            return

        for key, child in node.items():
            # 找到名为 "Picture" 的节点 (不管它在第几层)
            if key == "Picture" and isinstance(child, dict):
                shared_settings = {}

                # 1. 遍历收集所有图像模式下的子设置 (比如从 ECO 里提取出 Brightness, Contrast 等)
                for mode_name, mode_contents in child.items():
                    if mode_contents:  # 如果该模式有子菜单
                        shared_settings.update(mode_contents)

                # 2. 如果成功提取到了公共设置，则将其“克隆”到所有空的图像模式中
                if shared_settings:
                    for mode_name in child.keys():
                        # 使用 deepcopy 防止 Python 字典的内存指针引用污染
                        child[mode_name] = copy.deepcopy(shared_settings)

            # 继续往下寻找
            propagate_picture_settings(child)

    # 依次执行过滤规则
    split_newline_keys(tree)
    propagate_picture_settings(tree)

    return tree


def build_super_menu(file_path: str, root_sheet: str, output_json: str = None):
    """
    修改后的主函数：加入了业务规则清洗步骤
    """
    if not os.path.exists(file_path):
        print(f"[-] 文件不存在: {file_path}")
        return

    print(f"[*] 正在加载 Excel 并初始化全表索引...")
    excel_file = pd.ExcelFile(file_path)
    all_sheets_data = {}

    possible_cols = ['Main Menu', 'Sub Menu\n Level 1', 'Sub Menu\n Level 2', 'Sub Menu\n Level 3',
                     'Sub Menu\nLevel 3+']

    # 1. 动态表头解析所有 Sheet (保留上一版的动态表头逻辑)
    for sheet_name in excel_file.sheet_names:
        try:
            df_raw = pd.read_excel(file_path, sheet_name=sheet_name, header=None, nrows=15)
        except Exception:
            continue

        header_idx = -1
        for idx, row in df_raw.iterrows():
            row_values = [str(val).strip() for val in row.values]
            if 'Main Menu' in row_values:
                header_idx = idx
                break

        if header_idx == -1:
            continue

        df = pd.read_excel(file_path, sheet_name=sheet_name, header=header_idx)
        actual_cols = [c for c in possible_cols if c in df.columns]

        if not actual_cols:
            continue

        rows = df[actual_cols].values.tolist()
        all_sheets_data[sheet_name] = parse_sparse_tree(rows, len(actual_cols))
        print(f"    + 已成功解析 Sheet: '{sheet_name}'")

    if root_sheet not in all_sheets_data:
        print(f"[-] 错误: 根工作表 '{root_sheet}' 未找到。")
        return

    print(f"[*] 正在执行跨表引用链接 (Stitching)...")
    super_tree = resolve_tree_references(all_sheets_data[root_sheet], all_sheets_data)

    # ==========================================
    # [关键新增] 在输出前，应用业务逻辑规则进行最终修剪
    # ==========================================
    print(f"[*] 正在应用自定义业务规则 (处理语言换行、Picture子菜单扩散)...")
    final_tree = apply_custom_business_rules(super_tree)

    # 输出结果
    json_output = json.dumps(final_tree, ensure_ascii=False, indent=4)
    if output_json:
        with open(output_json, 'w', encoding='utf-8') as f:
            f.write(json_output)
        print(f"[+] 超级菜单树已生成: {output_json}")

    return final_tree


if __name__ == "__main__":
    # 配置
    FILE_PATH = r"C:\Users\Administrator\Desktop\test_clearn_osd_tree.xlsx"
    ROOT_SHEET = "First Layer"
    OUTPUT_FILE = "../super_menu_tree.json"

    build_super_menu(FILE_PATH, ROOT_SHEET, OUTPUT_FILE)