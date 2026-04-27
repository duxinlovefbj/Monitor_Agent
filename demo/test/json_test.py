import json


def print_json_tree(data, prefix=""):
    """
    递归打印 JSON 树状结构。
    :param data: JSON 列表或字典对象
    :param prefix: 当前行的前缀字符（用于控制缩进和树状层级展示）
    """
    if isinstance(data, list):
        for i, node in enumerate(data):
            is_last = (i == len(data) - 1)
            _print_node(node, prefix, is_last)
    elif isinstance(data, dict):
        _print_node(data, prefix, is_last=True)


def _print_node(node, prefix, is_last):
    # 定义树枝符号
    connector = "└── " if is_last else "├── "

    # 1. 提取核心节点名称
    name = node.get("name", "Unnamed Node")

    # 2. 动态提取并格式化非层级属性 (operation, Default, Range 及其他潜在的自定义键)
    attributes = []
    for key, value in node.items():
        if key not in ("name", "children"):
            # 处理列表中可能存在的换行符（如操作按键的换行），使其能在控制台单行整洁显示
            if isinstance(value, list):
                val_str = ", ".join([str(v).replace('\n', ' ↵ ') for v in value])
            else:
                val_str = str(value).replace('\n', ' ↵ ')
            attributes.append(f"[{key}: {val_str}]")

    attr_str = " ".join(attributes)
    if attr_str:
        attr_str = f"  {attr_str}"

    # 打印当前节点
    print(f"{prefix}{connector}{name}{attr_str}")

    # 3. 递归处理子节点 (children)
    if "children" in node:
        # 如果当前节点是最后一个节点，子节点的前缀使用空格对齐；否则使用垂直线连接
        child_prefix = prefix + ("    " if is_last else "│   ")
        print_json_tree(node["children"], child_prefix)


if __name__ == "__main__":
    # 将你提供的 JSON 数据作为字符串加载（此处截取部分作为示例，实际使用请替换为完整 JSON）

    try:
        # 在实际应用中，如果是读取外部文件，可以使用:
        with open(r'C:\Users\Administrator\PycharmProjects\Monitor_Agent\demo\excel_json\output_jsons\Main_Menu.json', 'r', encoding='utf-8') as f:
            parsed_data = json.load(f)

        print("OSD Menu Tree Structure:")
        print("=" * 60)
        print_json_tree(parsed_data)
        print("=" * 60)
    except json.JSONDecodeError as e:
        print(f"JSON 解析失败，请检查数据格式: {e}")