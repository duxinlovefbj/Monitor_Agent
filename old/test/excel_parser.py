import pandas as pd
import json


def parse_sparse_menu_to_json(data_rows, level_cols_count):
    """
    核心算法：利用状态机概念进行 Forward-fill 并构建嵌套树结构
    """
    tree = {}
    # current_path 用于记录当前追溯到的层级路径，长度等于层级数
    current_path = [None] * level_cols_count

    for row in data_rows:
        found_level_idx = -1

        # 1. 寻找当前行中，第一个有效（非空）的层级名称
        for i, val in enumerate(row):
            # 过滤掉 None、pandas 产生的 NaN，以及空白字符串
            if pd.notna(val) and str(val).strip() != "":
                current_path[i] = str(val).strip()
                found_level_idx = i
                break

        # 如果该行全为空（比如纯描述行、标题行或备注行），直接跳过
        if found_level_idx == -1:
            continue

        # 2. 关键阻断逻辑：当前层级发生变化时，必须把更深的子层级全部清除
        # 否则上一个父节点的子菜单会错误地作为当前节点的子菜单
        for i in range(found_level_idx + 1, level_cols_count):
            current_path[i] = None

        # 3. 将当前追踪到的层级路径挂载到 JSON 树 (Tree) 中
        current_node = tree
        for i in range(level_cols_count):
            node_name = current_path[i]
            if node_name is None:
                break  # 已经抵达当前行的最深子节点

            if node_name not in current_node:
                # 动态创建嵌套字典
                current_node[node_name] = {}
            # 指针向深层移动
            current_node = current_node[node_name]

    return json.dumps(tree, ensure_ascii=False, indent=4)


def convert_excel_to_menu_json(excel_path, sheet_name):
    """
    文件读取与数据预处理
    """
    # 读取 Excel，假设第一行为总说明（如“修改更新项目”），我们将 header 设为 1（即第二行的英文字段）
    df = pd.read_excel(excel_path, sheet_name=sheet_name, header=1)

    # 明确我们需要保留的层级列名称
    level_cols = [
        'Main Menu',
        'Sub Menu\n Level 1',
        'Sub Menu\n Level 2',
        'Sub Menu\n Level 3',
        'Sub Menu\nLevel 3+'
    ]

    # 防止有些 Sheet 没有配置 Level 3+，动态筛选出实际存在的列
    actual_level_cols = [col for col in level_cols if col in df.columns]

    # 仅提取层级列，转换为 list 以供核心算法按行遍历
    data_rows = df[actual_level_cols].values.tolist()

    # 丢入核心树状解析器
    json_result = parse_sparse_menu_to_json(data_rows, len(actual_level_cols))

    return json_result


if __name__ == "__main__":
    # 使用示例
    # file_path = "your_monitor_definition.xlsx"
    # json_output = convert_excel_to_menu_json(file_path, "Third Layer (Settings)")
    # print(json_output)

    # -------- 以下为使用你提供的数据样例进行的局部模拟测试 --------
    mock_data = [
        ('Gaming', 'Aim Stabilizer Sync', 'ON', None, None),
        (None, None, 'OFF', None, None),
        (None, 'Black Equalizer', None, None, None),
        (None, 'Super Resolution', None, None, None),
        (None, 'Display Mode', 'Full', None, None),
        (None, None, 'Aspect', None, None),
        (None, 'Overdrive', 'OFF', None, None),
        (None, None, 'Smart OD', None, None),
        (None, None, 'Picture quality', None, None),
        ('Picture', 'Standard', None, None, None),
        (None, 'Gamma', 'OFF', None, None),
        (None, None, 'Gamma 1', None, None),
        (None, 'Color Temperature', 'User Define', 'R', None),
        (None, None, None, 'G', None),
        (None, None, None, 'B', None)
    ]

    print("模拟输出测试结果：\n")
    print(parse_sparse_menu_to_json(mock_data, 5))