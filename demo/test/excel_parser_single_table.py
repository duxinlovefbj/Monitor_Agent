import pandas as pd
import json
import os

'''
    表格格式有问题，没办法完全依靠程序规范化
'''

def parse_sparse_tree(data_rows: list, level_cols_count: int) -> dict:
    """
    核心算法修复版：完整遍历稀疏矩阵，支持同一行定义多个层级。
    """
    tree = {}
    current_path = [None] * level_cols_count

    for row in data_rows:
        # 1. 寻找当前行第一个非空的列索引 (起始层级)
        first_valid_idx = -1
        for i in range(level_cols_count):
            val = row[i]
            if pd.notna(val) and str(val).strip() != "":
                first_valid_idx = i
                break

        # 全空行跳过
        if first_valid_idx == -1:
            continue

        # 2. 状态机重置：从首个有效层级开始，清空当前路径后续的所有记录
        # 例如：如果当前行从 Level 1 开始，则清空旧路径的 Level 1, Level 2, Level 3...
        for i in range(first_valid_idx, level_cols_count):
            current_path[i] = None

        # 3. 提取当前行所有的有效节点（关键修复：取消 break，读完本行）
        for i in range(first_valid_idx, level_cols_count):
            val = row[i]
            if pd.notna(val) and str(val).strip() != "":
                current_path[i] = str(val).strip()

        # 4. 将当前完整的路径挂载到树上
        current_node = tree
        for i in range(level_cols_count):
            node_name = current_path[i]
            if node_name is None:
                # 遇到 None 意味着当前行的层级已到底，停止向深层挂载
                break

            if node_name not in current_node:
                current_node[node_name] = {}
            # 指针向深层移动
            current_node = current_node[node_name]

    return tree


def extract_menu_from_excel(file_path: str, sheet_name: str, output_json_path: str = None) -> str:
    """
    读取指定的 Excel 工作表，提取菜单层级列并转换为 JSON。

    参数:
        file_path (str): .xlsx 文件路径
        sheet_name (str): 目标工作表名称
        output_json_path (str): 可选，如果提供，则将结果写入该文件
    """
    if not os.path.exists(file_path):
        raise FileNotFoundError(f"未找到文件：{file_path}，请检查路径是否正确。")

    print(f"[*] 正在读取文件: {file_path} -> 表单: {sheet_name}")

    try:
        # header=1 表示将 Excel 的第 2 行（索引1）作为 DataFrame 的列名
        df = pd.read_excel(file_path, sheet_name=sheet_name, header=1, engine="openpyxl")
    except ValueError as e:
        raise ValueError(f"读取工作表失败，请确认工作表 '{sheet_name}' 是否存在。错误信息: {e}")

    # 定义可能存在的层级列名池
    possible_level_cols = [
        'Main Menu',
        'Sub Menu\n Level 1',
        'Sub Menu\n Level 2',
        'Sub Menu\n Level 3',
        'Sub Menu\nLevel 3+'
    ]

    # 动态匹配当前表中实际存在的列名
    actual_cols = [col for col in possible_level_cols if col in df.columns]

    if not actual_cols:
        raise KeyError("在工作表中未找到任何预期的层级列（如 'Main Menu', 'Sub Menu\\n Level 1' 等）。")

    print(f"[*] 匹配到 {len(actual_cols)} 个层级列: {actual_cols}")

    # 提取目标列的数据，并转化为二位列表
    data_rows = df[actual_cols].values.tolist()

    # 构建树
    menu_tree = parse_sparse_tree(data_rows, len(actual_cols))

    # 转换为 JSON 字符串格式
    json_result = json.dumps(menu_tree, ensure_ascii=False, indent=4)

    # 如果指定了输出路径，则写入文件
    if output_json_path:
        try:
            with open(output_json_path, 'w', encoding='utf-8') as f:
                f.write(json_result)
            print(f"[+] 解析成功！JSON 结果已保存至: {output_json_path}")
        except IOError as e:
            print(f"[-] 写入文件失败: {e}")

    return json_result


if __name__ == "__main__":
    # ================= 配置区 =================
    # 请在此处填写你的实际文件路径和工作表名称
    EXCEL_FILE_PATH = r"C:\Users\Administrator\Desktop\test_clearn_osd_tree.xlsx"  # 使用 r 前缀防止转义
    TARGET_SHEET = "Third Layer (Settings)"
    OUTPUT_JSON = "menu_output.json"  # 输出的 json 文件名
    # ==========================================

    try:
        # 如果你只想打印到控制台，可以去掉 OUTPUT_JSON 参数
        result = extract_menu_from_excel(
            file_path=EXCEL_FILE_PATH,
            sheet_name=TARGET_SHEET,
            output_json_path=OUTPUT_JSON
        )
        # print("解析结果预览：\n", result[:500], "\n...\n") # 打印前500个字符预览
    except Exception as err:
        print(f"[-] 运行出现错误: {err}")