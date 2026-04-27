import json
import pandas as pd


def generate_deduped_tree_csv():
    json_path = 'super_menu_tree.json'
    excel_path = r"C:\Users\Administrator\Desktop\test_clearn_osd_tree.xlsx"
    output_csv_path = 'final_multi_language_tree.csv'

    # 1. 读取 JSON 菜单树
    try:
        with open(json_path, 'r', encoding='utf-8') as f:
            menu_tree = json.load(f)
    except FileNotFoundError:
        print(f"错误: 找不到文件 {json_path}")
        return

    # 2. 读取 Excel 文件
    print("正在读取 Excel 文件...")
    try:
        df = pd.read_excel(excel_path, sheet_name="Multi-Language", header=None)
    except Exception as e:
        print(f"读取 Excel 失败: {e}")
        return

    # 拆分表头与数据
    header_df = df.iloc[:3].copy()
    data_df = df.iloc[3:].copy().reset_index(drop=True)

    # ==========================================
    # 核心新增逻辑：3. 针对 Excel 数据进行全局去重
    # 判定标准：整行数据（所有语言的翻译列）完全相同，则只保留一条
    # ==========================================
    data_df_unique = data_df.drop_duplicates(keep='first').reset_index(drop=True)
    print(f"Excel去重完成: 从 {len(data_df)} 行精简至 {len(data_df_unique)} 独立翻译行。")

    # 4. 构建映射词典 (English -> List of Unique Rows)
    # 如果一个英文词条在去重后仍有多行，说明它存在不同的翻译版本
    excel_dict = {}
    for idx, row in data_df_unique.iterrows():
        eng_key = str(row[0]).strip()
        if eng_key not in excel_dict:
            excel_dict[eng_key] = []
        excel_dict[eng_key].append(row)

    output_rows = []
    used_eng_keys = set()
    ignore_keys = {"Default", "__Is_External_Link__", "__Source_Path__"}
    total_columns = len(df.columns)

    # 5. 深度优先遍历，复刻 JSON 结构
    def traverse_tree(node):
        if isinstance(node, dict):
            for key, value in node.items():
                if key not in ignore_keys:
                    clean_key = str(key).strip()

                    if clean_key in excel_dict:
                        # 如果匹配到，将该英文对应的【所有不同的翻译行】都追加进去
                        for unique_row in excel_dict[clean_key]:
                            output_rows.append(unique_row)
                        used_eng_keys.add(clean_key)
                    else:
                        # JSON 中有，但 Excel 中完全找不到的词条（留空补齐列数）
                        new_row = [clean_key] + [None] * (total_columns - 1)
                        output_rows.append(pd.Series(new_row, index=df.columns))

                    # 继续向下遍历子菜单
                    traverse_tree(value)

        elif isinstance(node, list):
            for item in node:
                traverse_tree(item)

    traverse_tree(menu_tree)

    # 6. 处理一次都没被匹配上的 Excel 孤儿词条（追加到末尾）
    unmatched_rows = []
    for idx, row in data_df_unique.iterrows():
        eng_key = str(row[0]).strip()
        if eng_key not in used_eng_keys:
            unmatched_rows.append(row)

    # 7. 拼接输出：表头 + 树状展开的主体 + 冗余未匹配项
    final_blocks = [header_df]
    if output_rows:
        final_blocks.append(pd.DataFrame(output_rows))
    if unmatched_rows:
        final_blocks.append(pd.DataFrame(unmatched_rows))

    final_df = pd.concat(final_blocks, ignore_index=True)

    # 8. 导出 CSV
    try:
        final_df.to_csv(output_csv_path, index=False, header=False, encoding='utf-8-sig')
        print(f"处理成功！修复重复项的完整 CSV 已输出至: {output_csv_path}")
    except Exception as e:
        print(f"写入 CSV 失败: {e}")


if __name__ == "__main__":
    generate_deduped_tree_csv()