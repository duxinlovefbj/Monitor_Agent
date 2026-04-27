import pandas as pd
import json
import re
import os
from typing import Dict, List, Any, Optional


class ExcelMenuParser:
    """
    Excel to JSON Converter for OSD Menu Hierarchies.
    Strictly follows the cross-validation, conditional splitting, and hierarchical tree mapping rules.
    """

    def __init__(self, excel_path: str):
        self.excel_path = excel_path
        # 读取所有的 sheet，填充空值为 None 以便后续判定
        self.sheets: Dict[str, pd.DataFrame] = pd.read_excel(excel_path, sheet_name=None)
        for sheet_name in self.sheets:
            self.sheets[sheet_name] = self.sheets[sheet_name].where(pd.notnull(self.sheets[sheet_name]), None)

        self.manual_subtrees: Dict[tuple, List[Dict[str, Any]]] = {}
        self.conditional_exports: List[Dict[str, Any]] = []
        self.standalone_sheets: List[str] = []

        # 记录被作为子树合并过的 sheet，避免在主 JSON 中重复输出
        self.embedded_sheets = set()
        # --- 新增：用于处理脏数据和拼写错误的自定义连接映射 ---
        self.custom_link_mapping: Dict[str, str] = {}
        self.reverse_link_mapping: Dict[str, str] = {}

    def set_manual_subtree(self, node_path: tuple, subtree: List[Dict[str, Any]]) -> None:
        """
        Rule 4.3: 设定手动替换的子树。
        :param node_path: 节点路径元组，如 ("Gaming", "Pixel Clean", "Start Time Delay")
        :param subtree: 需要替换的 JSON 子树列表
        """
        self.manual_subtrees[node_path] = subtree

    def set_custom_link_mapping(self, mapping: Dict[str, Any]) -> None:
        """
        融合精简版：取代原有的 hierarchy，支持将一个节点挂载到一个或多个工作表。
        格式: {"节点名称": ["目标表1", "目标表2", ...]} 或 {"节点名称": "目标表1"}
        """
        self.custom_link_mapping = {}
        for k, v in mapping.items():
            if isinstance(v, str):
                self.custom_link_mapping[str(k).strip()] = [str(v).strip()]
            else:
                self.custom_link_mapping[str(k).strip()] = [str(sheet).strip() for sheet in v]

    def add_conditional_export(self, target_filename: str, conditions: Dict[str, str], base_conditions: Dict[str, str] = None) -> None:
        """
        双向切割逻辑更新：
        - conditions: HDR 的专属条件。提取 SDR(Main) 时会丢弃这些。
        - base_conditions: SDR 的专属条件。提取 HDR 时会丢弃这些。
        """
        self.conditional_exports.append({
            "target_filename": target_filename,
            "target_conditions": conditions,
            "base_conditions": base_conditions or {}
        })

    def _get_filtered_sheets(self, drop_conditions: Dict[str, str]) -> Dict[str, pd.DataFrame]:
        """返回一份去除了指定 drop_conditions 的完整 sheets 副本"""
        filtered = {}
        for name, df in self.sheets.items():
            if df.empty or not drop_conditions:
                filtered[name] = df.copy()
                continue

            mask = pd.Series([False] * len(df), index=df.index)
            for col, val in drop_conditions.items():
                clean_col = col.strip()
                if clean_col in df.columns:
                    mask = mask | df[clean_col].astype(str).str.contains(str(val).strip(), na=False, regex=False)

            # 保留未匹配条件的行（即丢弃匹配行）
            filtered[name] = df[~mask].reset_index(drop=True)
        return filtered

    def _build_full_json_tree(self, sheets_dict: Dict[str, pd.DataFrame]) -> List[Dict[str, Any]]:
        """基于过滤好的 sheets 字典，组装出一棵完整的独立 JSON 树"""
        sheet_trees = {name: self._build_tree(df) for name, df in sheets_dict.items()}
        self.embedded_sheets = set()  # 每次建树时独立重置挂载记录

        # 交叉验证与挂载
        for name, tree in sheet_trees.items():
            self._link_cross_sheet(tree, sheet_trees)

        main_json_data = []
        for name, tree in sheet_trees.items():
            # 核心修复 1：明确拒绝 standalone_sheets 混入主树！
            if name not in self.embedded_sheets and name not in self.standalone_sheets:
                main_json_data.extend(tree)

        self._apply_manual_subtrees(main_json_data)
        self._cleanup_empty_children(main_json_data)

        return main_json_data

    def generate_jsons(self, output_dir: str = "./output") -> None:
        """主执行链路：支持多环境（SDR/HDR）独立生成完整树"""
        if not os.path.exists(output_dir):
            os.makedirs(output_dir)

        self.process_picture_mode("Picture Mode", output_dir)

        # 1. 优先独立导出单表 (Rule 4.5)
        for sheet_name in self.standalone_sheets:
            if sheet_name in self.sheets:
                tree = self._build_tree(self.sheets[sheet_name])
                with open(os.path.join(output_dir, f"{sheet_name}.json"), 'w', encoding='utf-8') as f:
                    json.dump(tree, f, ensure_ascii=False, indent=2)

        # 2. 如果没有条件切割配置，默认生成一个原版 Main_Menu.json
        if not self.conditional_exports:
            full_tree = self._build_full_json_tree(self.sheets)
            with open(os.path.join(output_dir, "Main_Menu.json"), 'w', encoding='utf-8') as f:
                json.dump(full_tree, f, ensure_ascii=False, indent=2)
            print(f"转换完成，JSON 文件已输出至 {output_dir} 目录。")
            return

        # 3. 核心修复 2：双向生成两套完整环境 (HDR 环境 和 SDR 环境)
        for config in self.conditional_exports:
            # 制作 HDR 完整树（全表复制 -> 丢弃 SDR 独有行 -> 组装）
            hdr_sheets = self._get_filtered_sheets(config['base_conditions'])
            hdr_tree = self._build_full_json_tree(hdr_sheets)
            with open(os.path.join(output_dir, config['target_filename']), 'w', encoding='utf-8') as f:
                json.dump(hdr_tree, f, ensure_ascii=False, indent=2)

            # 制作 SDR 完整树（全表复制 -> 丢弃 HDR 独有行 -> 组装）
            main_sheets = self._get_filtered_sheets(config['target_conditions'])
            main_tree = self._build_full_json_tree(main_sheets)
            with open(os.path.join(output_dir, "Main_Menu.json"), 'w', encoding='utf-8') as f:
                json.dump(main_tree, f, ensure_ascii=False, indent=2)

        print(f"转换完成，JSON 文件已输出至 {output_dir} 目录。")

    def add_standalone_sheet(self, sheet_name: str) -> None:
        """Rule 4.5: 指定独立导出的工作表名称"""
        self.standalone_sheets.append(sheet_name)

    def _build_tree(self, df: pd.DataFrame) -> List[Dict[str, Any]]:
        """执行 Rule 3.1 & 4.1 & 4.2: 将平面 DataFrame 转换为深层树状结构"""
        if df.empty: return []

        tree = []
        cols = df.columns.tolist()

        # 确定层级列的边界：从 'Main Menu' 开始，到 'Range' / 'Default' / '是否立即套用' 之前
        try:
            start_idx = cols.index('Main Menu')
        except ValueError:
            return []  # 如果没有 Main Menu，放弃构建（或可扩展抛出异常）

        end_markers = ['Range', 'Default', '是否\n立即套用', 'Function\nScale', 'Remark']
        end_indices = [cols.index(c) for c in end_markers if c in cols]
        end_idx = min(end_indices) if end_indices else len(cols)

        hierarchy_cols = cols[start_idx:end_idx]

        for _, row in df.iterrows():
            current_level = tree
            last_node = None

            # Rule 4.1: Operation 解析
            operation_list = None
            if 'Operation' in cols and not pd.isna(row['Operation']):
                op_str = str(row['Operation'])
                operation_list = [op.strip() for op in op_str.split('/')]

            # 遍历层级结构
            for i, col in enumerate(hierarchy_cols):
                val = row[col]
                # 这里额外拦截被意外转化为字符串的 'nan'
                if pd.isna(val) or str(val).strip().lower() == 'nan':
                    continue  # 遇到空值代表层级在此行结束

                # 查找当前层级是否已存在同名节点
                node = next((n for n in current_level if n['name'] == str(val)), None)
                if not node:
                    node = {'name': str(val), 'children': []}
                    current_level.append(node)

                # Rule 4.1: 仅对顶级节点(即 Main Menu 列对应的节点)挂载 Operation
                if i == 0 and operation_list is not None:
                    node['operation'] = operation_list

                last_node = node
                current_level = node['children']

            # Rule 4.2: 为最后的子节点附加 Default 等属性
            if last_node is not None:
                if 'Default' in cols and not pd.isna(row['Default']) and str(
                        row['Default']).strip().lower() != 'nan':
                    last_node['Default'] = str(row['Default'])
                if 'Range' in cols and not pd.isna(row['Range']) and str(row['Range']).strip().lower() != 'nan':
                    last_node['Range'] = str(row['Range'])

        return tree

    def _link_cross_sheet(self, tree: List[Dict[str, Any]], all_sheet_trees: Dict[str, List[Dict[str, Any]]]) -> None:
        """执行 Rule 2.1: 支持 1对多 的交叉验证与子树挂载，并自动套一层工作表大分类节点"""

        def get_mapped_sheet_names(node_name: str) -> List[str]:
            clean_node_name = str(node_name).strip()

            # 1. 优先检查自定义映射 (1对多挂载)
            if hasattr(self, 'custom_link_mapping') and clean_node_name in self.custom_link_mapping:
                return self.custom_link_mapping[clean_node_name]

            # 2. 正则 fallback
            m = re.match(r'^(.*?)\s*\((.*?)\)$', clean_node_name)
            if m:
                return [f"{m.group(2).strip()}({m.group(1).strip()})"]
            return []

        for node in tree:
            target_sheets = get_mapped_sheet_names(node['name'])
            if target_sheets:
                if 'children' not in node:
                    node['children'] = []

                # 遍历所有目标表，按顺序进行包装与挂载
                for sheet_name in target_sheets:
                    if sheet_name in all_sheet_trees:
                        # 智能提取真实大类名称：将 "Settings(Main Menu)" 转换为干净的 "Settings"
                        # m = re.match(r'^(.*?)\s*\((.*?)\)$', sheet_name)
                        # category_name = m.group(1).strip() if m else sheet_name

                        category_name = sheet_name

                        # 将子表数据包裹在一个带有 category_name 的父节点内
                        wrapper_node = {
                            "name": category_name,
                            "children": all_sheet_trees[sheet_name]
                        }

                        # 使用 append 将这个包装节点作为整体塞进去，而不是用 extend 平铺
                        node['children'].append(wrapper_node)
                        self.embedded_sheets.add(sheet_name)

            if 'children' in node and node['children']:
                self._link_cross_sheet(node['children'], all_sheet_trees)

    def _apply_manual_subtrees(self, tree: List[Dict[str, Any]]) -> None:
        """执行 Rule 4.3: 手动节点替换 (支持深层递归扫描与局部路径匹配)"""

        def traverse_and_replace(current_nodes: List[Dict[str, Any]], current_path: List[str]):
            for node in current_nodes:
                # 记录从根节点到当前节点的完整路径
                path_to_here = current_path + [node['name']]

                # 遍历用户定义的所有手动替换规则
                for target_path_tuple, new_subtree in self.manual_subtrees.items():
                    target_path = list(target_path_tuple)

                    # 核心逻辑：只要当前路径的“尾部”匹配了目标路径，就执行替换！
                    # 比如当前路径是 [..., 'Pixel Clean', 'Start Time Delay']
                    # 目标路径是 ['Start Time Delay']，完美命中后缀
                    if len(path_to_here) >= len(target_path) and path_to_here[-len(target_path):] == target_path:
                        node['children'] = new_subtree
                        break  # 命中后跳出当前规则循环

                # 继续向更深层的子节点递归扫描
                if 'children' in node:
                    traverse_and_replace(node['children'], path_to_here)

        # 启动全树递归扫描
        traverse_and_replace(tree, [])

    def _cleanup_empty_children(self, tree: List[Dict[str, Any]]) -> None:
        """清理无意义的空 children 数组，保证 JSON 整洁"""
        for node in tree:
            if 'children' in node:
                if not node['children']:
                    del node['children']
                else:
                    self._cleanup_empty_children(node['children'])

    def process_picture_mode(self, sheet_name: str = "Picture Mode", output_dir: str = "./output") -> None:
        """
        专属逻辑：处理 Picture Mode 特殊表，按模式将参数聚合，生成独立的 JSON。
        """
        if sheet_name not in self.sheets:
            return

        df = self.sheets[sheet_name]

        # 还原完整的二维数组以自上而下扫描
        raw_columns = df.columns.tolist()
        clean_cols = [None if str(c).startswith('Unnamed:') else c for c in raw_columns]
        all_rows = [clean_cols] + df.values.tolist()

        output_data = {"SDR mode": {}, "HDR mode": {}}
        current_table = None
        header_idx = -1
        mode_mapping = {}

        for row in all_rows:
            if all(pd.isnull(x) or str(x).strip() in ('', 'None', 'nan') for x in row):
                continue

            row_strs = [str(x).strip() for x in row if pd.notnull(x)]

            # 1. 动态检测是否进入了目标小表
            is_header = False
            for marker in ['SDR mode', 'HDR mode']:
                if marker in row_strs:
                    current_table = marker
                    header_idx = next(i for i, x in enumerate(row) if str(x).strip() == marker)
                    mode_mapping = {}

                    for i in range(header_idx + 1, len(row)):
                        val = row[i]
                        if pd.notnull(val):
                            val_str = str(val).strip()
                            if val_str not in ('', 'None', 'nan') and '工廠' not in val_str:
                                mode_mapping[i] = val_str
                                if val_str not in output_data[current_table]:
                                    output_data[current_table][val_str] = {}
                    is_header = True
                    break

            if is_header:
                continue

            # 2. 遇到不需要的表头关闭收集
            if header_idx != -1 and header_idx < len(row):
                cell_val = str(row[header_idx]).strip()
                if cell_val == '6-axis Color':
                    current_table = None
                    continue

            # 3. 提取参数
            if current_table and mode_mapping:
                if header_idx >= len(row):
                    continue

                param_name = row[header_idx]
                if pd.isnull(param_name):
                    continue

                param_name_str = str(param_name).strip()

                if param_name_str in ('', 'None', 'nan') or param_name_str.startswith('註'):
                    continue

                for idx, mode_name in mode_mapping.items():
                    if idx < len(row):
                        val = row[idx]
                        if pd.isnull(val) or str(val).strip().lower() == 'nan':
                            val = None

                        # 特殊规则：亮度设为50
                        if current_table == 'SDR mode' and param_name_str == 'Brightness':
                            if mode_name == 'sRGB' or 'Color Space' in mode_name:
                                val = 50

                        output_data[current_table][mode_name][param_name_str] = val

        # 4. 输出 JSON
        if not os.path.exists(output_dir):
            os.makedirs(output_dir)

        output_path = os.path.join(output_dir, "Picture_Mode.json")
        with open(output_path, 'w', encoding='utf-8') as f:
            json.dump(output_data, f, ensure_ascii=False, indent=2)

if __name__ == "__main__":
    # 实例化解析器并加载 Excel
    parser = ExcelMenuParser(r"C:\Users\Administrator\Desktop\Aorus OSD Tree_FO27Q24G_Q28G_20260401_tpv_cleaned_flattened.xlsx")

    # [A, [B, C]] 结构
    parser.set_custom_link_mapping({
        "Main Menu(Setting)": [
            "Settings(Main Menu)",
            "AI Assistant(Main Menu)",
            "Game Assist(Main Menu)",
            "AI OLED Care Pro(Main Menu)",
            "System(Main Menu)"
        ]
    })

    # [规则 4.3] 手动为特定节点添加/替换子树
    # 比如在 "Main Menu(Settings)" 下寻找 "Gaming", 再找 "Pixel Clean"，并在它的子节点中附加列表
    custom_subtree = [
        {"name": "0 min", "Default": "0 min"},
        {"name": "15 min", "Default": "0 min"},
        {"name": "30 min", "Default": "0 min"},
        {"name": "45 min", "Default": "0 min"},
        {"name": "60 min", "Default": "0 min"},
        {"name": "75 min", "Default": "0 min"},
        {"name": "90 min", "Default": "0 min"},
        {"name": "105 min", "Default": "0 min"},
        {"name": "120 min", "Default": "0 min"},
    ]
    parser.set_manual_subtree(
        node_path=("Start Time Delay",),
        subtree=custom_subtree
    )

    # [规则 4.4] 条件切割导出
    # 填入双向特征：生成 HDR 时丢弃 base 的条件；生成 Main(SDR) 时丢弃 target 的条件。
    parser.add_conditional_export(
        target_filename="HDR.json",
        conditions={
            "Remark": "HDR時顯示",
            "Main Menu": "Picture ( HDR/HLG 時)"
        },
        base_conditions={
            "Remark": "SDR時顯示",
            "Main Menu": "Picture ( SDR 時)"
        }
    )

    # [规则 4.5] 单独导出特定工作表
    # 这张表不会被合并到主树里，直接成为独立文件
    parser.add_standalone_sheet("Standby Menu")

    # 执行完整的生成流
    parser.generate_jsons("./output_jsons")