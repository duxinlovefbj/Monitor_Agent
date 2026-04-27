import json
import os
import tkinter as tk
from tkinter import ttk, messagebox
from collections import deque


class OSDMenuPathfinder:
    def __init__(self, json_path="super_menu_tree.json"):
        self.tree_data = self.load_json(json_path)

    def load_json(self, path):
        # 尝试读取外部JSON，如果没有则使用默认（对应您提供的结构）
        if os.path.exists(path):
            try:
                with open(path, 'r', encoding='utf-8') as f:
                    return json.load(f)
            except Exception as e:
                print(f"读取文件失败: {e}，将使用备用空结构")
        else:
            print(f"未找到 {path}，请确保文件在根目录。")
        return {}

    def get_valid_children(self, node_dict):
        """获取所有正常的菜单选项（排除 Default 和以 __ 开头的属性）"""
        if not isinstance(node_dict, dict):
            return []
        return [k for k in node_dict.keys() if k != "Default" and not str(k).startswith("__")]

    def get_default_item(self, node_dict):
        """获取进入某一层级时光标默认停留的位置"""
        children = self.get_valid_children(node_dict)
        if not children:
            return None

        if "Default" in node_dict:
            def_val = node_dict["Default"]
            # 如果 Default 指定的项存在于子节点中，优先返回
            if isinstance(def_val, str) and def_val in children:
                return def_val
            # 注意：在 Overdrive 中 Default 是一个字典，无法直接定位，退而求其次选第一个

        # 否则选物理排序第一项
        return children[0]

    def get_node_at_path(self, path_tuple):
        """根据路径元组获取对应的 JSON 节点"""
        curr = self.tree_data
        for p in path_tuple:
            curr = curr.get(p, {})
        return curr

    def path_to_state(self, path_tuple):
        """
        将目标树路径转换为 UI 状态。
        状态定义:
        1. ("IDLE",) -> 根节点
        2. ("MAIN_MENU",) -> 按下中键后的快捷键等待页面
        3. ("LIST", menu_path, focused_item) -> 正常的列表菜单状态
        """
        if not path_tuple:
            return ("IDLE",)

        if path_tuple == ("Main Menu",):
            return ("MAIN_MENU",)

        # 根目录第一层级的快捷方式 (比如 Crosshair, Input)
        if len(path_tuple) == 1:
            node = self.get_node_at_path(path_tuple)
            return ("LIST", path_tuple, self.get_default_item(node))

        # Main Menu 下的快捷方式 (比如 Settings, GameAssist)
        if len(path_tuple) == 2 and path_tuple[0] == "Main Menu":
            node = self.get_node_at_path(path_tuple)
            return ("LIST", path_tuple, self.get_default_item(node))

        # 常规列表子项：状态为在其父级菜单中，光标落在目标项上
        return ("LIST", path_tuple[:-1], path_tuple[-1])

    def is_target(self, state, target_path):
        """判断当前状态是否满足目标路径"""
        if not target_path:
            return state == ("IDLE",)

        if target_path == ("Main Menu",):
            return state == ("MAIN_MENU",)

        # 情况 1：光标直接落在目标项上
        if state[0] == "LIST" and state[1] == target_path[:-1] and state[2] == target_path[-1]:
            return True

        # 情况 2：目标项是一个跨层级快捷入口（如 Settings），此时只要进入该菜单即算到达
        if state[0] == "LIST" and state[1] == target_path:
            return True

        return False

    def get_neighbors(self, state):
        """获取当前状态通过上下左右中键能到达的所有邻居状态"""
        neighbors = []

        if state == ("IDLE",):
            neighbors.append(("长按中键", ("LIST", ("Turn Off",), None)))
            neighbors.append(("中键", ("MAIN_MENU",)))
            neighbors.append(("左键", self.path_to_state(("Crosshair",))))
            neighbors.append(("右键", self.path_to_state(("Input",))))
            neighbors.append(("上键", self.path_to_state(("Black Equalizer",))))
            neighbors.append(("下键", self.path_to_state(("Picture Mode",))))

        elif state == ("MAIN_MENU",):
            neighbors.append(("中键", ("IDLE",)))  # 再次中键退出
            neighbors.append(("左键", self.path_to_state(("Main Menu", "Crosshair"))))
            neighbors.append(("右键", self.path_to_state(("Main Menu", "GameAssist"))))
            neighbors.append(("上键", self.path_to_state(("Main Menu", "Settings"))))
            neighbors.append(("下键", self.path_to_state(("Main Menu", "Turn off"))))

        elif state[0] == "LIST":
            menu_path = state[1]
            focused_item = state[2]
            node = self.get_node_at_path(menu_path)
            children = self.get_valid_children(node)

            # 同级上下移动
            if focused_item in children:
                idx = children.index(focused_item)
                if idx > 0:
                    neighbors.append(("上键", ("LIST", menu_path, children[idx - 1])))
                if idx < len(children) - 1:
                    neighbors.append(("下键", ("LIST", menu_path, children[idx + 1])))

            # 右键：进入更深层级
            if focused_item is not None:
                child_node = node.get(focused_item, {})
                child_children = self.get_valid_children(child_node)
                # 只有当包含子菜单时才能通过右键进入
                if child_children:
                    next_path = menu_path + (focused_item,)
                    neighbors.append(("右键", ("LIST", next_path, self.get_default_item(child_node))))

            # 左键：返回上一层级
            if len(menu_path) == 2 and menu_path[0] == "Main Menu":
                neighbors.append(("左键", ("MAIN_MENU",)))
            elif len(menu_path) == 1:
                neighbors.append(("左键", ("IDLE",)))
            elif len(menu_path) > 1:
                # 返回父级列表，并将光标落在刚退出的项上
                neighbors.append(("左键", ("LIST", menu_path[:-1], menu_path[-1])))

        return neighbors

    def find_shortest_path(self, start_path, end_path):
        """广度优先搜索寻找最短路径"""
        start_state = self.path_to_state(start_path)

        # 边界情况
        if self.is_target(start_state, end_path):
            return ["当前已在目标位置，无需操作"]

        queue = deque([(start_state, [])])
        visited = set()
        visited.add(start_state)

        while queue:
            current_state, path_actions = queue.popleft()

            for action, next_state in self.get_neighbors(current_state):
                if next_state not in visited:
                    new_actions = path_actions + [action]
                    if self.is_target(next_state, end_path):
                        return new_actions

                    visited.add(next_state)
                    queue.append((next_state, new_actions))

        return ["无法找到有效路径"]


class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("OSD 菜单操作路径计算器")
        self.geometry("900x600")

        self.pathfinder = OSDMenuPathfinder()

        self.setup_ui()
        self.populate_trees()

    def setup_ui(self):
        main_frame = ttk.Frame(self, padding="10")
        main_frame.pack(fill=tk.BOTH, expand=True)

        # 顶部树状图区域
        trees_frame = ttk.Frame(main_frame)
        trees_frame.pack(fill=tk.BOTH, expand=True, pady=(0, 10))

        # 起点选择区
        start_frame = ttk.LabelFrame(trees_frame, text="1. 选择起点节点", padding="5")
        start_frame.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=(0, 5))

        self.start_tree = ttk.Treeview(start_frame, selectmode="browse")
        self.start_tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        vsb1 = ttk.Scrollbar(start_frame, orient="vertical", command=self.start_tree.yview)
        vsb1.pack(side=tk.RIGHT, fill=tk.Y)
        self.start_tree.configure(yscrollcommand=vsb1.set)

        # 终点选择区
        end_frame = ttk.LabelFrame(trees_frame, text="2. 选择终点节点", padding="5")
        end_frame.pack(side=tk.RIGHT, fill=tk.BOTH, expand=True, padx=(5, 0))

        self.end_tree = ttk.Treeview(end_frame, selectmode="browse")
        self.end_tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        vsb2 = ttk.Scrollbar(end_frame, orient="vertical", command=self.end_tree.yview)
        vsb2.pack(side=tk.RIGHT, fill=tk.Y)
        self.end_tree.configure(yscrollcommand=vsb2.set)

        # 控制及结果区
        bottom_frame = ttk.Frame(main_frame)
        bottom_frame.pack(fill=tk.X, pady=5)

        calc_btn = ttk.Button(bottom_frame, text="计算最短路径 ➔", command=self.calculate_path)
        calc_btn.pack(pady=10)

        self.result_text = tk.Text(bottom_frame, height=5, font=("Microsoft YaHei", 12), state="disabled")
        self.result_text.pack(fill=tk.X)

    def _insert_nodes(self, tree_widget, parent_id, node_dict, current_path):
        for key in self.pathfinder.get_valid_children(node_dict):
            child_path = current_path + [key]
            # 使用 json.dumps 将路径列表转为字符串作为 item 的唯一 iid
            item_id = json.dumps(child_path)
            tree_widget.insert(parent_id, "end", iid=item_id, text=key)
            self._insert_nodes(tree_widget, item_id, node_dict[key], child_path)

    def populate_trees(self):
        # 填充起点树和终点树
        for tree in (self.start_tree, self.end_tree):
            root_id = json.dumps([])
            tree.insert("", "end", iid=root_id, text="[初始待机状态 (Root)]")
            self._insert_nodes(tree, root_id, self.pathfinder.tree_data, [])
            tree.item(root_id, open=True)  # 默认展开根节点

    def calculate_path(self):
        start_sel = self.start_tree.selection()
        end_sel = self.end_tree.selection()

        if not start_sel or not end_sel:
            messagebox.showwarning("提示", "请同时选择起点和终点节点！")
            return

        start_path = tuple(json.loads(start_sel[0]))
        end_path = tuple(json.loads(end_sel[0]))

        path_actions = self.pathfinder.find_shortest_path(start_path, end_path)

        self.result_text.config(state="normal")
        self.result_text.delete(1.0, tk.END)
        self.result_text.insert(tk.END, " \n ➔ ".join(path_actions))
        self.result_text.config(state="disabled")


if __name__ == "__main__":
    app = App()
    app.mainloop()