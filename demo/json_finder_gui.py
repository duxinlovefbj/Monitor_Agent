import json
import os
import tkinter as tk
from tkinter import ttk, messagebox
from collections import deque

from demo.lib.key_pcb_control import MonitorController


class OSDMenuPathfinder:
    def __init__(self, json_path="MO27Q28G.json"):
        self.tree_data = self.load_json(json_path)

    def load_json(self, path):
        if os.path.exists(path):
            try:
                with open(path, 'r', encoding='utf-8') as f:
                    return json.load(f)
            except Exception as e:
                print(f"读取文件失败: {e}，将使用备用空结构")
        return {}

    def get_valid_children(self, node_dict):
        if not isinstance(node_dict, dict):
            return []

        # 规则1：包含 Look Only 的节点，作为叶子节点不再向下展开
        if node_dict.get("Ps") == "Look Only":
            return []

        valid_keys = []
        for k, v in node_dict.items():
            # 过滤掉系统控制键和内部状态属性
            if k in ["Default", "Ps"] or str(k).startswith("__"):
                continue

            # 规则2：彻底过滤掉包含 "Ps": "HDR" 的子级分支
            if isinstance(v, dict) and v.get("Ps") == "HDR":
                continue

            valid_keys.append(k)

        return valid_keys

    def get_default_item(self, node_dict):
        children = self.get_valid_children(node_dict)
        if not children:
            return None
        if "Default" in node_dict:
            def_val = node_dict["Default"]
            if isinstance(def_val, str) and def_val in children:
                return def_val
        return children[0]

    def get_node_at_path(self, path_tuple):
        curr = self.tree_data
        for p in path_tuple:
            curr = curr.get(p, {})
        return curr

    def path_to_state(self, path_tuple):
        if not path_tuple:
            return ("IDLE",)
        if path_tuple == ("Main Menu",):
            return ("MAIN_MENU",)
        if len(path_tuple) == 1:
            node = self.get_node_at_path(path_tuple)
            return ("LIST", path_tuple, self.get_default_item(node))
        if len(path_tuple) == 2 and path_tuple[0] == "Main Menu":
            node = self.get_node_at_path(path_tuple)
            return ("LIST", path_tuple, self.get_default_item(node))
        return ("LIST", path_tuple[:-1], path_tuple[-1])

    def is_target(self, state, target_path):
        if not target_path:
            return state == ("IDLE",)
        if target_path == ("Main Menu",):
            return state == ("MAIN_MENU",)
        if state[0] == "LIST" and state[1] == target_path[:-1] and state[2] == target_path[-1]:
            return True
        if state[0] == "LIST" and state[1] == target_path:
            return True
        return False

    def get_neighbors(self, state):
        neighbors = []
        if state == ("IDLE",):
            neighbors.append(("长按中键", ("LIST", ("Turn Off",), None)))
            neighbors.append(("中键", ("MAIN_MENU",)))
            neighbors.append(("左键", self.path_to_state(("Volume",))))
            neighbors.append(("右键", self.path_to_state(("Input",))))
            neighbors.append(("上键", self.path_to_state(("Black Equalizer",))))
            neighbors.append(("下键", self.path_to_state(("Picture Mode",))))

        elif state == ("MAIN_MENU",):
            neighbors.append(("中键", ("IDLE",)))
            # 【核心修复点】：将你原版代码中的 "Exit" 改为 "OLED Care"
            neighbors.append(("左键", self.path_to_state(("Main Menu", "OLED Care"))))
            neighbors.append(("右键", self.path_to_state(("Main Menu", "GameAssist"))))
            neighbors.append(("上键", self.path_to_state(("Main Menu", "Settings"))))
            neighbors.append(("下键", self.path_to_state(("Main Menu", "Power Off"))))

        elif state[0] == "LIST":
            menu_path = state[1]
            focused_item = state[2]
            node = self.get_node_at_path(menu_path)
            children = self.get_valid_children(node)

            if focused_item in children:
                idx = children.index(focused_item)
                if idx > 0:
                    neighbors.append(("上键", ("LIST", menu_path, children[idx - 1])))
                if idx < len(children) - 1:
                    neighbors.append(("下键", ("LIST", menu_path, children[idx + 1])))

            if focused_item is not None:
                child_node = node.get(focused_item, {})
                child_children = self.get_valid_children(child_node)
                if child_children:
                    next_path = menu_path + (focused_item,)
                    neighbors.append(("右键", ("LIST", next_path, self.get_default_item(child_node))))

            if len(menu_path) == 2 and menu_path[0] == "Main Menu":
                neighbors.append(("左键", ("MAIN_MENU",)))
            elif len(menu_path) == 1:
                neighbors.append(("左键", ("IDLE",)))
            elif len(menu_path) > 1:
                neighbors.append(("左键", ("LIST", menu_path[:-1], menu_path[-1])))

        return neighbors

    def find_shortest_path(self, start_path, end_path):
        start_state = self.path_to_state(start_path)
        if self.is_target(start_state, end_path):
            return "SAME", []

        queue = deque([(start_state, [])])
        visited = set([start_state])

        while queue:
            current_state, path_data = queue.popleft()
            for action, next_state in self.get_neighbors(current_state):
                if next_state not in visited:
                    new_path = path_data + [(action, next_state)]
                    # 容错：每次衍生出新状态即检查是否到达
                    if self.is_target(next_state, end_path):
                        return "OK", new_path
                    visited.add(next_state)
                    queue.append((next_state, new_path))

        return "ERROR", []


class PathVisualizer(tk.Toplevel):
    def __init__(self, parent, start_state, path_data):
        super().__init__(parent)
        self.title("路径操作可视化")
        self.geometry("900x600")
        self.canvas = tk.Canvas(self, bg="#2b2b2b")
        self.canvas.pack(fill=tk.BOTH, expand=True)

        self.dpad_ids = {}
        self.draw_dpad()

        self.path_data = path_data
        self.step_index = 0

        self.curr_x = 80
        self.curr_y = 50

        self.draw_node(self.state_to_text(start_state), self.curr_x, self.curr_y, is_start=True)
        self.after(1000, self.animate_step)

    def round_rect(self, x1, y1, x2, y2, radius=15, **kwargs):
        points = [x1 + radius, y1, x2 - radius, y1, x2, y1, x2, y1 + radius, x2, y2 - radius, x2, y2,
                  x2 - radius, y2, x1 + radius, y2, x1, y2, x1, y2 - radius, x1, y1 + radius, x1, y1]
        return self.canvas.create_polygon(points, **kwargs, smooth=True)

    def draw_dpad(self):
        cx, cy = 700, 300
        w, h = 60, 60
        gap = 5
        btn_color = "#555555"

        self.dpad_ids["上键"] = self.round_rect(cx - w / 2, cy - h - gap - w / 2, cx + w / 2, cy - gap - w / 2,
                                                fill=btn_color)
        self.dpad_ids["下键"] = self.round_rect(cx - w / 2, cy + gap + w / 2, cx + w / 2, cy + h + gap + w / 2,
                                                fill=btn_color)
        self.dpad_ids["左键"] = self.round_rect(cx - w - gap - w / 2, cy - h / 2, cx - gap - w / 2, cy + h / 2,
                                                fill=btn_color)
        self.dpad_ids["右键"] = self.round_rect(cx + gap + w / 2, cy - h / 2, cx + w + gap + w / 2, cy + h / 2,
                                                fill=btn_color)
        self.dpad_ids["中键"] = self.round_rect(cx - w / 2, cy - h / 2, cx + w / 2, cy + h / 2, fill=btn_color)
        self.dpad_ids["长按中键"] = self.dpad_ids["中键"]

        self.canvas.create_text(cx, cy - h - gap, text="UP", fill="white", font=("Arial", 12, "bold"))
        self.canvas.create_text(cx, cy + h + gap, text="DOWN", fill="white", font=("Arial", 12, "bold"))
        self.canvas.create_text(cx - w - gap, cy, text="LEFT", fill="white", font=("Arial", 12, "bold"))
        self.canvas.create_text(cx + w + gap, cy, text="RIGHT", fill="white", font=("Arial", 12, "bold"))
        self.canvas.create_text(cx, cy, text="OK", fill="white", font=("Arial", 12, "bold"))

    def state_to_text(self, state):
        if state[0] == "IDLE":
            return "待机 / 黑屏"
        elif state[0] == "MAIN_MENU":
            return "主菜单快捷圈"
        else:
            menu_path = state[1]
            item = state[2]
            parent_name = menu_path[-1] if menu_path else "Root"
            return f"[{parent_name}]\n➔ {item}"

    def draw_node(self, text, x, y, is_start=False):
        w, h = 180, 50
        bg_color = "#ff9800" if is_start else "#00bcd4"
        self.round_rect(x, y, x + w, y + h, radius=10, fill=bg_color, outline="white", width=2)
        self.canvas.create_text(x + w / 2, y + h / 2, text=text, fill="white", font=("Microsoft YaHei", 10, "bold"),
                                justify="center")

    def animate_step(self):
        if self.step_index >= len(self.path_data):
            self.canvas.create_text(400, self.curr_y + 100, text="✅ 路径演示与硬件操作完毕！", fill="#4CAF50",
                                    font=("Microsoft YaHei", 16, "bold"))
            return

        action, next_state = self.path_data[self.step_index]
        btn_id = self.dpad_ids.get(action)

        # ==========================================================
        # 核心集成：在这里触发硬件指令，异步执行不卡顿 UI
        # ==========================================================
        MonitorController.press(action, manufacturer="KTC", async_mode=True)

        # 严谨性时序控制：
        # 如果是长按(耗时 2s)，UI 必须等待至少 2500ms 再执行下一步动画和下一步硬件指令
        # 如果是短按(耗时 0.2s)，保持原有的 900ms 动画节奏即可
        next_step_delay = 2500 if action == "长按中键" else 900

        if btn_id:
            self.canvas.itemconfig(btn_id, fill="#4CAF50")

        next_x, next_y = self.curr_x, self.curr_y + 80
        if next_y > 500:
            next_y = 50
            next_x += 220

        def show_next_node():
            if btn_id:
                self.canvas.itemconfig(btn_id, fill="#555555")

            if next_x == self.curr_x:
                self.canvas.create_line(self.curr_x + 90, self.curr_y + 50, next_x + 90, next_y, arrow=tk.LAST,
                                        fill="white", width=2)
            else:
                self.canvas.create_line(self.curr_x + 180, self.curr_y + 25, next_x, next_y + 25, arrow=tk.LAST,
                                        fill="white", width=2)

            self.draw_node(self.state_to_text(next_state), next_x, next_y)
            self.curr_x, self.curr_y = next_x, next_y
            self.step_index += 1

            # 使用动态计算的延迟时间，确保上一条 USB 硬件指令完全释放
            self.after(next_step_delay, self.animate_step)

        self.after(300, show_next_node)


class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("OSD 菜单操作路径计算器 (可视化加强版)")
        self.geometry("900x600")

        self.pathfinder = OSDMenuPathfinder()
        self.visualizer_window = None

        self.setup_ui()
        self.populate_trees()

    def setup_ui(self):
        main_frame = ttk.Frame(self, padding="10")
        main_frame.pack(fill=tk.BOTH, expand=True)

        trees_frame = ttk.Frame(main_frame)
        trees_frame.pack(fill=tk.BOTH, expand=True, pady=(0, 10))

        start_frame = ttk.LabelFrame(trees_frame, text="1. 选择起点节点", padding="5")
        start_frame.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=(0, 5))
        self.start_tree = ttk.Treeview(start_frame, selectmode="browse")
        self.start_tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        vsb1 = ttk.Scrollbar(start_frame, orient="vertical", command=self.start_tree.yview)
        vsb1.pack(side=tk.RIGHT, fill=tk.Y)
        self.start_tree.configure(yscrollcommand=vsb1.set)

        end_frame = ttk.LabelFrame(trees_frame, text="2. 选择终点节点", padding="5")
        end_frame.pack(side=tk.RIGHT, fill=tk.BOTH, expand=True, padx=(5, 0))
        self.end_tree = ttk.Treeview(end_frame, selectmode="browse")
        self.end_tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        vsb2 = ttk.Scrollbar(end_frame, orient="vertical", command=self.end_tree.yview)
        vsb2.pack(side=tk.RIGHT, fill=tk.Y)
        self.end_tree.configure(yscrollcommand=vsb2.set)

        bottom_frame = ttk.Frame(main_frame)
        bottom_frame.pack(fill=tk.X, pady=5)

        calc_btn = ttk.Button(bottom_frame, text="计算最短路径并演示 ➔", command=self.calculate_path)
        calc_btn.pack(pady=10)

        self.result_text = tk.Text(bottom_frame, height=3, font=("Microsoft YaHei", 12), state="disabled")
        self.result_text.pack(fill=tk.X)

    def _insert_nodes(self, tree_widget, parent_id, node_dict, current_path):
        for key in self.pathfinder.get_valid_children(node_dict):
            child_path = current_path + [key]
            item_id = json.dumps(child_path)
            tree_widget.insert(parent_id, "end", iid=item_id, text=key)
            self._insert_nodes(tree_widget, item_id, node_dict[key], child_path)

    def populate_trees(self):
        for tree in (self.start_tree, self.end_tree):
            root_id = json.dumps([])
            tree.insert("", "end", iid=root_id, text="[待机 / 黑屏状态]")
            self._insert_nodes(tree, root_id, self.pathfinder.tree_data, [])
            tree.item(root_id, open=True)

    def calculate_path(self):
        start_sel = self.start_tree.selection()
        end_sel = self.end_tree.selection()

        if not start_sel or not end_sel:
            messagebox.showwarning("提示", "请同时选择起点和终点节点！")
            return

        start_path = tuple(json.loads(start_sel[0]))
        end_path = tuple(json.loads(end_sel[0]))

        status, path_data = self.pathfinder.find_shortest_path(start_path, end_path)

        self.result_text.config(state="normal")
        self.result_text.delete(1.0, tk.END)

        if status == "SAME":
            self.result_text.insert(tk.END, "当前已在目标位置，无需操作")
            self.result_text.config(state="disabled")
            return
        elif status == "ERROR":
            self.result_text.insert(tk.END, "无法找到有效路径")
            self.result_text.config(state="disabled")
            return

        actions_only = [item[0] for item in path_data]
        self.result_text.insert(tk.END, " ➔ ".join(actions_only))
        self.result_text.config(state="disabled")

        if self.visualizer_window is not None and self.visualizer_window.winfo_exists():
            self.visualizer_window.destroy()

        start_state = self.pathfinder.path_to_state(start_path)
        self.visualizer_window = PathVisualizer(self, start_state, path_data)


if __name__ == "__main__":
    app = App()
    app.mainloop()