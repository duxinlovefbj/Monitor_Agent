import json
import os
import sqlite3
import tkinter as tk
from tkinter import ttk, messagebox, simpledialog
import time
from demo.lib.app.path_finder import OSDMenuPathfinder
from demo.lib.app.path_viewer import PathVisualizer
import hashlib
from tkinter import filedialog
from demo.lib.llm.llm_scanner import OSDSemanticScanner # 引入我们刚写的 LLM 模块
from demo.lib.ca410.ca410_control import CA410Controller
import csv
from datetime import datetime

# ==========================================
# 主界面程序 (引入时间线执行队列架构)
# ==========================================
class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("Monitor Auto GUI")
        self.geometry("1200x1200")

        self.pathfinder = OSDMenuPathfinder()
        self.visualizer_window = None

        # 核心：混合执行队列 (存储字典 dict)
        self.execution_queue = []
        self.macro_data_cache = {}

        self.manufacturer_var = tk.StringVar(value="KTC")  # 默认 KTC

        self.current_json_path = ""
        self.current_json_hash = ""
        self.semantic_mapping = {}  # 存储 LLM 解析出来的意图字典

        # 绑定 StringVar 用于 UI 双向绑定
        self.api_key_var = tk.StringVar()
        self.model_var = tk.StringVar(value="qwen/qwen3.5-122b-a10b")

        self.init_db()
        self.setup_ui()
        self.populate_trees()
        self.load_db_data()

        self.picture_mode_defaults = {}
        self.current_signal_mode = "SDR mode"
        self.current_picture_mode = "ECO"

        self.current_run_id = None
        self.current_measurement_csv_path = None


    def init_db(self):
        self.conn = sqlite3.connect("osd_paths.db")
        self.cursor = self.conn.cursor()
        # 表1：基础动作宏库 (纯粹存放连续的按键)
        self.cursor.execute('''CREATE TABLE IF NOT EXISTS saved_macros
                             (id INTEGER PRIMARY KEY, name TEXT, actions TEXT)''')
        # 兼容旧数据库：新增智能寻路入口字段
        self._ensure_column("saved_macros", "entry_path", "TEXT")
        self._ensure_column("saved_macros", "entry_intent", "TEXT")
        # 表2：复合指令库 (存放由寻路和宏任意组合的时间线序列)
        self.cursor.execute('''CREATE TABLE IF NOT EXISTS saved_sequences
                             (id INTEGER PRIMARY KEY, name TEXT, sequence_json TEXT)''')
        # 表3：系统设置表 (存 API Key 和 Model)
        self.cursor.execute('''CREATE TABLE IF NOT EXISTS settings
                                     (key TEXT PRIMARY KEY, value TEXT)''')
        # 表4：LLM 语义解析缓存表 (通过文件内容的 Hash 值映射，避免重复调 API)
        self.cursor.execute('''CREATE TABLE IF NOT EXISTS llm_cache
                                     (json_hash TEXT PRIMARY KEY, mapping_data TEXT)''')
        self.conn.commit()

    def _ensure_column(self, table_name, column_name, column_type):
        """
        SQLite 兼容升级：如果旧表没有字段，就自动补字段。
        """
        self.cursor.execute(f"PRAGMA table_info({table_name})")
        columns = [row[1] for row in self.cursor.fetchall()]

        if column_name not in columns:
            self.cursor.execute(
                f"ALTER TABLE {table_name} ADD COLUMN {column_name} {column_type}"
            )
            self.conn.commit()

    def setup_ui(self):
        self.paned = ttk.PanedWindow(self, orient=tk.HORIZONTAL)
        self.paned.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)

        left_frame = ttk.Frame(self.paned)
        right_frame = ttk.Frame(self.paned)
        self.paned.add(left_frame, weight=3)
        self.paned.add(right_frame, weight=1)

        # ====== 模块0: 全局文件与大模型配置 ======
        config_frame = ttk.LabelFrame(left_frame, text="0. 全局配置 (JSON 与 大模型)", padding="5")
        config_frame.pack(fill=tk.X, pady=(0, 5))

        # JSON 文件加载行
        file_row = ttk.Frame(config_frame)
        file_row.pack(fill=tk.X, pady=2)
        ttk.Button(file_row, text="📁 载入 OSD JSON 文件", command=self.load_json_file).pack(side=tk.LEFT, padx=5)
        self.lbl_file_path = ttk.Label(file_row, text="当前未加载文件", foreground="gray")
        self.lbl_file_path.pack(side=tk.LEFT, padx=5)
        ttk.Button(
            file_row,
            text="📁 载入 Picture Mode 默认值",
            command=self.load_picture_mode_defaults_file
        ).pack(side=tk.LEFT, padx=5)

        # API 配置行
        api_row = ttk.Frame(config_frame)
        api_row.pack(fill=tk.X, pady=2)
        ttk.Label(api_row, text="NVIDIA API Key:").pack(side=tk.LEFT, padx=5)
        ttk.Entry(api_row, textvariable=self.api_key_var, width=30, show="*").pack(side=tk.LEFT, padx=5)
        ttk.Label(api_row, text="Model:").pack(side=tk.LEFT, padx=5)
        ttk.Entry(api_row, textvariable=self.model_var, width=25).pack(side=tk.LEFT, padx=5)
        ttk.Button(api_row, text="💾 保存配置", command=self.save_api_settings).pack(side=tk.LEFT, padx=5)

        # LLM 触发行动
        llm_row = ttk.Frame(config_frame)
        llm_row.pack(fill=tk.X, pady=5)
        ttk.Button(llm_row, text="🤖 对当前 JSON 进行语义提取 (自动查缓存)", command=self.trigger_llm_scan).pack(
            side=tk.LEFT, padx=5)
        self.lbl_llm_status = ttk.Label(llm_row, text="未提取", foreground="gray")
        self.lbl_llm_status.pack(side=tk.LEFT, padx=5)

        # 在 left_frame 的最开始添加
        vendor_frame = ttk.LabelFrame(left_frame, text="0. 硬件厂商选择", padding="5")
        vendor_frame.pack(fill=tk.X, pady=(0, 5))
        ttk.Radiobutton(vendor_frame, text="KTC 通道", variable=self.manufacturer_var, value="KTC").pack(side=tk.LEFT,
                                                                                                         padx=20)
        ttk.Radiobutton(vendor_frame, text="TPV / MOKA 通道", variable=self.manufacturer_var, value="TPV").pack(
            side=tk.LEFT, padx=20)


        # ====== 模块1: 绝对寻路模块 ======

        path_frame = ttk.LabelFrame(left_frame, text="1. 绝对位置寻路", padding="5")
        path_frame.pack(fill=tk.X, pady=(0, 5))

        trees_container = ttk.Frame(path_frame)
        trees_container.pack(fill=tk.X, expand=True)

        start_frame = ttk.Frame(trees_container)
        start_frame.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(0, 5))
        ttk.Label(start_frame, text="起点:").pack(anchor=tk.W)
        self.start_tree = ttk.Treeview(start_frame, selectmode="browse", height=5)
        self.start_tree.pack(fill=tk.X, expand=True)

        end_frame = ttk.Frame(trees_container)
        end_frame.pack(side=tk.RIGHT, fill=tk.X, expand=True, padx=(5, 0))
        ttk.Label(end_frame, text="终点:").pack(anchor=tk.W)
        self.end_tree = ttk.Treeview(end_frame, selectmode="browse", height=5)
        self.end_tree.pack(fill=tk.X, expand=True)

        ttk.Button(path_frame, text="➕ 将选定【寻路路径】添加到执行队列", command=self.add_path_to_queue).pack(pady=5)

        # ====== 模块2: 相对盲按动作与系统指令 ======
        macro_frame = ttk.LabelFrame(left_frame, text="2. 相对盲按与系统级测试指令", padding="5")
        macro_frame.pack(fill=tk.X, pady=5)

        # --- 2.1 物理按键参数化控制区 ---
        key_row = ttk.Frame(macro_frame)
        key_row.pack(fill=tk.X, pady=2)
        ttk.Label(key_row, text="物理按键:").pack(side=tk.LEFT)

        self.key_val_var = tk.StringVar(value="中键")
        ttk.Combobox(key_row, textvariable=self.key_val_var,
                     values=["上键", "下键", "左键", "右键", "中键"],
                     state="readonly", width=5).pack(side=tk.LEFT, padx=5)

        self.key_duration_var = tk.StringVar(value="短按")
        ttk.Combobox(key_row, textvariable=self.key_duration_var,
                     values=["短按", "长按"],
                     state="readonly", width=5).pack(side=tk.LEFT, padx=5)

        ttk.Button(key_row, text="➕ 增加按键", command=self.add_custom_key_to_queue).pack(side=tk.LEFT, padx=5)

        # --- 2.2 软件与测试指令区 ---
        test_row = ttk.Frame(macro_frame)
        test_row.pack(fill=tk.X, pady=4)
        ttk.Label(test_row, text="测试指令:").pack(side=tk.LEFT)

        # 1. 休眠控制 (5s步进)
        self.sleep_var = tk.StringVar(value="5s")
        ttk.Combobox(test_row, textvariable=self.sleep_var,
                     values=["5s", "10s", "15s"],
                     state="readonly", width=5).pack(side=tk.LEFT, padx=(5, 0))
        ttk.Button(test_row, text="➕ 休眠",
                   command=lambda: self.add_action_to_queue(f"休眠{self.sleep_var.get()}")).pack(side=tk.LEFT,
                                                                                                 padx=(0, 5))

        # 2. 全屏 Pattern 渲染控制
        self.pattern_var = tk.StringVar(value="White")
        ttk.Combobox(test_row, textvariable=self.pattern_var,
                     values=["Red", "Green", "Blue", "White", "Black", "DisplayHDR", "32阶Gamma"],
                     state="readonly", width=14).pack(side=tk.LEFT, padx=(5, 0))
        ttk.Button(test_row, text="➕ 画面",
                   command=lambda: self.add_action_to_queue(f"测试画面({self.pattern_var.get()})")).pack(side=tk.LEFT,
                                                                                                         padx=(0, 5))

        # 3. 系统级 HDR 切换与硬件测量 (原功能保留)
        ttk.Button(test_row, text="➕ 切换HDR(Win+Alt+B)",
                   command=lambda: self.add_action_to_queue("切换系统HDR")).pack(side=tk.LEFT, padx=5)
        ttk.Button(test_row, text="➕ 测量亮度",
                   command=lambda: self.add_action_to_queue("测量亮度")).pack(side=tk.LEFT, padx=5)

        # --- 2.3 宏引入区 (保留原有逻辑不变) ---
        combo_container = ttk.Frame(macro_frame)
        combo_container.pack(fill=tk.X, pady=5)
        ttk.Label(combo_container, text="引入已存宏库: ").pack(side=tk.LEFT)
        self.combo_macros = ttk.Combobox(combo_container, state="readonly", width=20)
        self.combo_macros.pack(side=tk.LEFT, padx=5)
        ttk.Button(combo_container, text="➕ 将选定【宏】添加到执行队列", command=self.add_macro_to_queue).pack(
            side=tk.LEFT)

        # ====== 模块 2.5: 跨机型动态意图 (依赖 LLM) ======
        intent_frame = ttk.LabelFrame(left_frame, text="2.5 跨机型动态意图 (自适应不同 JSON 路径)", padding="5")
        intent_frame.pack(fill=tk.X, pady=5)

        self.intent_var = tk.StringVar()
        self.combo_intents = ttk.Combobox(intent_frame, textvariable=self.intent_var, state="readonly", width=35)

        # 绑定友好的中文显示名称与底层的 INTENT_KEY
        # TODO 修改一下需要更详细的意图寻路逻辑
        self.intent_map = {
            "亮度": "INTENT_BRIGHTNESS",
            "对比度": "INTENT_CONTRAST",
            "标准模式": "INTENT_PICTURE_MODE_STANDARD",
            "sRGB模式": "INTENT_PICTURE_MODE_SRGB",
            "色温冷色": "INTENT_COLOR_TEMP_COOL",
            "色温自然": "INTENT_COLOR_TEMP_NATURAL",
            "色温标准": "INTENT_COLOR_TEMP_NORMAL",
            "色温暖色": "INTENT_COLOR_TEMP_WARM",
            "Gamma OFF": "INTENT_GAMMA_OFF",
            "Gamma 1.8": "INTENT_GAMMA_1.8",
            "Gamma 2.0": "INTENT_GAMMA_2.0",
            "Gamma 2.2": "INTENT_GAMMA_2.2",
            "Gamma 2.4": "INTENT_GAMMA_2.4",
            "Gamma 2.6": "INTENT_GAMMA_2.6",
            "重置所有": "INTENT_RESET_ALL",
            "信号源切换": "INTENT_INPUT_SOURCE"
        }
        self.combo_intents['values'] = list(self.intent_map.keys())
        self.combo_intents.pack(side=tk.LEFT, padx=5)

        ttk.Button(intent_frame, text="➕ 将选定【动态意图】添加到队列", command=self.add_intent_to_queue).pack(
            side=tk.LEFT, padx=5)

        # ====== 模块3: 混合编排时间线 (核心) ======
        queue_frame = ttk.LabelFrame(left_frame, text="3. 混合执行队列时间线 (可自由组合执行顺序)", padding="5")
        queue_frame.pack(fill=tk.BOTH, expand=True, pady=5)

        self.queue_listbox = tk.Listbox(queue_frame, font=("Microsoft YaHei", 10), selectmode=tk.SINGLE)
        self.queue_listbox.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=(0, 5))

        q_btn_frame = ttk.Frame(queue_frame)
        q_btn_frame.pack(side=tk.RIGHT, fill=tk.Y)
        ttk.Button(q_btn_frame, text="↑ 上移", command=self.move_queue_up).pack(fill=tk.X, pady=2)
        ttk.Button(q_btn_frame, text="↓ 下移", command=self.move_queue_down).pack(fill=tk.X, pady=2)
        ttk.Button(q_btn_frame, text="❌ 删除选中", command=self.remove_queue_item).pack(fill=tk.X, pady=2)
        ttk.Button(q_btn_frame, text="🗑 清空队列", command=self.clear_queue).pack(fill=tk.X, pady=10)

        # 底部操作按钮
        bottom_frame = ttk.Frame(left_frame)
        bottom_frame.pack(fill=tk.X, pady=5)
        ttk.Button(bottom_frame, text="▶ 执行当前队列", command=self.run_current_queue).pack(side=tk.LEFT, padx=5,
                                                                                             ipadx=10, ipady=5)
        ttk.Button(bottom_frame, text="💾 存为智能基础宏", command=self.save_queue_as_macro).pack(
            side=tk.RIGHT, padx=5)
        ttk.Button(bottom_frame, text="💾 存为完整复合指令", command=self.save_queue_as_sequence).pack(side=tk.RIGHT,
                                                                                                      padx=5)

        # 在 App 类的 setup_ui 方法中，找到 bottom_frame 之后添加：
        # ====== 模块 4: 实时测量数据/日志 ======
        log_frame = ttk.LabelFrame(left_frame, text="4. 测量数据实时监控", padding="5")
        log_frame.pack(fill=tk.BOTH, expand=True, pady=5)

        self.log_text = tk.Text(log_frame, height=8, font=("Consolas", 10), state=tk.DISABLED, bg="#1e1e1e",
                                fg="#d4d4d4")
        self.log_text.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

        scrollbar = ttk.Scrollbar(log_frame, command=self.log_text.yview)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        self.log_text.config(yscrollcommand=scrollbar.set)

        # ====== 右侧：数据库持久化面板 ======
        self.notebook = ttk.Notebook(right_frame)
        self.notebook.pack(fill=tk.BOTH, expand=True)

        # Tab 1: 复合指令
        tab_seq = ttk.Frame(self.notebook)
        self.notebook.add(tab_seq, text="📦 复合指令库")
        self.db_seq_listbox = tk.Listbox(tab_seq, font=("Microsoft YaHei", 10))
        self.db_seq_listbox.pack(fill=tk.BOTH, expand=True, pady=5)
        seq_btn_frame = ttk.Frame(tab_seq)
        seq_btn_frame.pack(fill=tk.X)
        ttk.Button(seq_btn_frame, text="导入到队列", command=self.load_sequence_to_queue).pack(side=tk.LEFT,
                                                                                               expand=True, fill=tk.X,
                                                                                               padx=2)
        ttk.Button(seq_btn_frame, text="删除", command=self.delete_sequence).pack(side=tk.RIGHT, expand=True, fill=tk.X,
                                                                                  padx=2)

        # Tab 2: 基础动作宏
        tab_macros = ttk.Frame(self.notebook)
        self.notebook.add(tab_macros, text="🧩 基础宏库")
        self.db_macro_listbox = tk.Listbox(tab_macros, font=("Microsoft YaHei", 10))
        self.db_macro_listbox.pack(fill=tk.BOTH, expand=True, pady=5)
        macro_btn_frame = ttk.Frame(tab_macros)
        macro_btn_frame.pack(fill=tk.X)
        ttk.Button(macro_btn_frame, text="删除宏", command=self.delete_macro).pack(fill=tk.X, padx=2)

    def sync_pathfinder_context(self):
        """
        把主程序维护的当前状态同步给 pathfinder。
        """
        self.pathfinder.picture_mode_defaults = self.picture_mode_defaults
        self.pathfinder.set_picture_mode_context(
            signal_mode=self.current_signal_mode,
            picture_mode=self.current_picture_mode
        )

        self.log_message(
            f"🧭 当前寻路上下文: {self.current_signal_mode} / {self.current_picture_mode}"
        )

    def load_picture_mode_defaults_file(self):
        filepath = filedialog.askopenfilename(
            title="选择 Picture Mode 默认值 JSON 文件",
            filetypes=[("JSON Files", "*.json")]
        )
        if not filepath:
            return

        try:
            with open(filepath, "r", encoding="utf-8") as f:
                self.picture_mode_defaults = json.load(f)

            self.sync_pathfinder_context()
            self.log_message(f"✅ 成功加载 Picture Mode 默认值: {os.path.basename(filepath)}")

        except Exception as e:
            messagebox.showerror("加载失败", f"Picture Mode 默认值 JSON 读取失败：\n{e}")

    # ====== 树形结构填充 ======
    def _insert_nodes(self, tree_widget, parent_id, node_data, current_path):
        """兼容新 JSON 格式的 UI 树形图渲染"""
        # 利用刚刚重写的方法获取所有有效的子节点名称
        children_names = self.pathfinder.get_valid_children(node_data)

        for key in children_names:
            child_path = current_path + [key]
            item_id = json.dumps(child_path)

            # 在 UI 中插入节点
            tree_widget.insert(parent_id, "end", iid=item_id, text=key)

            # 获取该子节点的完整字典数据并继续递归
            child_node = self.pathfinder.get_node_at_path(child_path)
            self._insert_nodes(tree_widget, item_id, child_node, child_path)

    def _apply_state_side_effects_by_path(self, e_path):
        """
        执行寻路后的状态副作用。
        目前主要用于 Picture Mode 默认值同步。
        """
        new_pm = self.infer_picture_mode_from_path(e_path)
        if new_pm:
            self.current_picture_mode = new_pm
            self.sync_pathfinder_context()
            self.log_message(f"🎨 Picture Mode 状态更新为: {new_pm}")

        if self.is_reset_path(e_path):
            self.current_picture_mode = "ECO"
            self.sync_pathfinder_context()
            self.log_message("♻️ 检测到 Reset，Picture Mode 状态恢复为: ECO")

    def _apply_state_side_effects_by_intent(self, intent_key, e_path):
        """
        执行动意图后的状态副作用。
        """
        new_pm = self.infer_picture_mode_from_intent(intent_key)
        if new_pm:
            self.current_picture_mode = new_pm
            self.sync_pathfinder_context()
            self.log_message(f"🎨 Picture Mode 状态更新为: {new_pm}")

        if intent_key == "INTENT_RESET_ALL" or self.is_reset_path(e_path):
            self.current_picture_mode = "ECO"
            self.sync_pathfinder_context()
            self.log_message("♻️ 检测到 Reset All，Picture Mode 状态恢复为: ECO")

    def populate_trees(self):
        for tree in (self.start_tree, self.end_tree):
            root_id = json.dumps([])
            tree.insert("", "end", iid=root_id, text="[待机 / 黑屏状态]")
            self._insert_nodes(tree, root_id, self.pathfinder.tree_data, [])
            tree.item(root_id, open=True)

    # ====== 队列管理逻辑 ======
    def refresh_queue_ui(self):
        self.queue_listbox.delete(0, tk.END)
        for idx, item in enumerate(self.execution_queue):
            self.queue_listbox.insert(tk.END, f"{idx + 1}. {item['display']}")

    def add_path_to_queue(self):
        start_sel = self.start_tree.selection()
        end_sel = self.end_tree.selection()
        if not start_sel or not end_sel:
            messagebox.showwarning("提示", "请先在上方树形图中选择起点和终点！")
            return

        start_path = tuple(json.loads(start_sel[0]))
        end_path = tuple(json.loads(end_sel[0]))

        start_str = start_path[-1] if start_path else "待机"
        end_str = end_path[-1] if end_path else "待机"

        self.execution_queue.append({
            "type": "path",
            "start": start_path,
            "end": end_path,
            "display": f"[寻路模块] {start_str} ➔ {end_str}"
        })
        self.refresh_queue_ui()
        self.queue_listbox.yview(tk.END)

    def add_action_to_queue(self, act_name):
        self.execution_queue.append({
            "type": "action",
            "val": act_name,
            "display": f"[单个动作] 按下: {act_name}"
        })
        self.refresh_queue_ui()
        self.queue_listbox.yview(tk.END)

    def add_custom_key_to_queue(self):
        """将带有参数属性的物理按键转义后推入队列"""
        key = self.key_val_var.get()
        duration = self.key_duration_var.get()

        # 暂时为了兼容现有底层执行逻辑，将参数拼接回原本的字符串格式
        # 例如：选择“上键”和“长按”，输出为“长按上键”
        act_name = key if duration == "短按" else f"长按{key}"
        self.add_action_to_queue(act_name)

    def add_macro_to_queue(self):
        macro_name = self.combo_macros.get()
        if not macro_name or macro_name not in self.macro_data_cache:
            messagebox.showwarning("提示", "请先从下拉框选择一个宏！")
            return

        macro_obj = self.macro_data_cache[macro_name]

        self.execution_queue.append({
            "type": "macro",
            "name": macro_name,
            "actions": macro_obj.get("actions", []),
            "entry_path": macro_obj.get("entry_path"),
            "entry_intent": macro_obj.get("entry_intent"),
            "display": f"[智能宏] {macro_name}"
        })

        self.refresh_queue_ui()
        self.queue_listbox.yview(tk.END)

    def add_intent_to_queue(self):
        display_name = self.intent_var.get()
        if not display_name:
            messagebox.showwarning("提示", "请先从下拉框选择一个意图！")
            return

        intent_key = self.intent_map[display_name]
        self.execution_queue.append({
            "type": "intent",
            "intent_key": intent_key,
            "display": f"[动态意图] 自动寻路 ➔ {display_name.split(' ')[0]}"
        })
        self.refresh_queue_ui()
        self.queue_listbox.yview(tk.END)

    def move_queue_up(self):
        sel = self.queue_listbox.curselection()
        if not sel: return
        idx = sel[0]
        if idx > 0:
            self.execution_queue[idx - 1], self.execution_queue[idx] = self.execution_queue[idx], self.execution_queue[
                idx - 1]
            self.refresh_queue_ui()
            self.queue_listbox.selection_set(idx - 1)

    def move_queue_down(self):
        sel = self.queue_listbox.curselection()
        if not sel: return
        idx = sel[0]
        if idx < len(self.execution_queue) - 1:
            self.execution_queue[idx + 1], self.execution_queue[idx] = self.execution_queue[idx], self.execution_queue[
                idx + 1]
            self.refresh_queue_ui()
            self.queue_listbox.selection_set(idx + 1)

    def remove_queue_item(self):
        sel = self.queue_listbox.curselection()
        if not sel: return
        del self.execution_queue[sel[0]]
        self.refresh_queue_ui()

    def clear_queue(self):
        self.execution_queue.clear()
        self.refresh_queue_ui()

    def log_message(self, message):
        """在 GUI 日志框中追加信息"""
        self.log_text.config(state=tk.NORMAL)
        timestamp = time.strftime("%H:%M:%S")
        self.log_text.insert(tk.END, f"[{timestamp}] {message}\n")
        self.log_text.see(tk.END)
        self.log_text.config(state=tk.DISABLED)

    def save_ca410_measurement_to_csv(
            self,
            full_data: dict,
            action_name="测量亮度",
            queue_display="",
            source_type="PathVisualizer",
            source_name="执行队列"
    ):
        """
        保存 CA410 单次测量结果到 CSV。
        - 每轮执行队列一个 CSV 文件
        - 自动追加
        - 自动写表头
        - 自动清洗 -99999999
        - 自动附加测试上下文
        """
        import csv
        import os
        from datetime import datetime

        if not full_data:
            self.log_message("❌ CSV 写入失败：测量数据为空。")
            return

        # 1. 如果当前轮次还没有 CSV，就创建一个
        if not getattr(self, "current_measurement_csv_path", None):
            result_dir = "measurement_results"
            os.makedirs(result_dir, exist_ok=True)

            self.current_run_id = datetime.now().strftime("%Y%m%d_%H%M%S")
            self.current_measurement_csv_path = os.path.join(
                result_dir,
                f"ca410_results_{self.current_run_id}.csv"
            )

            self.log_message(f"📁 本轮测量 CSV: {self.current_measurement_csv_path}")

        # 2. 清洗 CA410 原始数据
        invalid_values = {
            -99999999,
            -99999999.0,
            "-99999999",
            "-99999999.000000"
        }

        cleaned_data = {}
        for key, value in full_data.items():
            if value in invalid_values:
                cleaned_data[key] = ""
            else:
                cleaned_data[key] = value

        # 3. 追加上下文
        context_data = {
            "run_id": getattr(self, "current_run_id", ""),
            "saved_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "action_name": action_name,
            "source_type": source_type,
            "source_name": source_name,
            "queue_display": queue_display,
            "signal_mode": getattr(self, "current_signal_mode", ""),
            "picture_mode": getattr(self, "current_picture_mode", ""),
            "manufacturer": self.manufacturer_var.get() if hasattr(self, "manufacturer_var") else "",
            "osd_json_file": os.path.basename(self.current_json_path) if getattr(self, "current_json_path", "") else "",
        }

        row = {}
        row.update(context_data)
        row.update(cleaned_data)

        # 4. 写入 CSV
        file_exists = os.path.exists(self.current_measurement_csv_path)

        try:
            with open(self.current_measurement_csv_path, mode="a", newline="", encoding="utf-8-sig") as f:
                writer = csv.DictWriter(f, fieldnames=list(row.keys()))

                if not file_exists:
                    writer.writeheader()

                writer.writerow(row)

            self.log_message(
                f"✅ 测量数据已写入 CSV | "
                f"Lv={row.get('lv', '')} | "
                f"CCT={row.get('cct', '')} | "
                f"Duv={row.get('duv', '')}"
            )

        except Exception as e:
            self.log_message(f"❌ CSV 写入失败: {e}")

    # ====== 核心解析与执行引擎 ======
    def run_current_queue(self):
        if not self.execution_queue:
            messagebox.showwarning("提示", "队列为空，请先添加指令模块！")
            return

        self.sync_pathfinder_context()
        self.current_run_id = None
        self.current_measurement_csv_path = None

        current_vendor = self.manufacturer_var.get()
        final_path_data = []
        start_state = None

        # 新逻辑：
        # 复合指令被视为完整测试步骤。
        # 每个寻路/意图/智能宏入口都默认从待机状态出发。
        standby_path = ()

        for idx, item in enumerate(self.execution_queue):
            item_type = item["type"]

            if item_type == "path":
                e_path = tuple(item["end"])

                status, path_data = self.pathfinder.find_shortest_path(standby_path, e_path)
                if status == "ERROR":
                    messagebox.showerror(
                        "寻路错误",
                        f"计算中止！队列第 {idx + 1} 项【绝对寻路】失败。"
                    )
                    return

                if start_state is None:
                    start_state = self.pathfinder.path_to_state(standby_path)

                final_path_data.extend(path_data)
                self._apply_state_side_effects_by_path(e_path)

            elif item_type == "intent":
                if not self.semantic_mapping:
                    messagebox.showerror(
                        "依赖缺失",
                        "尚未提取意图映射！\n请先点击上方按钮进行 LLM 语义提取或加载缓存。"
                    )
                    return

                intent_key = item["intent_key"]
                target_path_list = self.semantic_mapping.get(intent_key)

                if not target_path_list:
                    messagebox.showerror(
                        "适配失败",
                        f"当前机型的 JSON 中未找到：{intent_key}\n该机型可能无此功能。"
                    )
                    return

                e_path = tuple(target_path_list)

                status, path_data = self.pathfinder.find_shortest_path(standby_path, e_path)
                if status == "ERROR":
                    messagebox.showerror(
                        "动态寻路错误",
                        f"无法从待机状态自动路由至意图：{intent_key}"
                    )
                    return

                if start_state is None:
                    start_state = self.pathfinder.path_to_state(standby_path)

                final_path_data.extend(path_data)
                self._apply_state_side_effects_by_intent(intent_key, e_path)

            elif item_type == "action":
                if start_state is None:
                    start_state = ("MANUAL", "队列起点")

                final_path_data.append(
                    (item["val"], ("MANUAL", f"相对动作\n[{item['val']}]"))
                )

            elif item_type == "macro":
                if start_state is None:
                    start_state = ("MANUAL", f"队列起点\n[{item['name']}]")

                # 1. 智能宏入口：固定路径入口
                entry_path = item.get("entry_path")
                if entry_path:
                    e_path = tuple(entry_path)

                    status, path_data = self.pathfinder.find_shortest_path(standby_path, e_path)
                    if status == "ERROR":
                        messagebox.showerror(
                            "宏入口寻路错误",
                            f"队列第 {idx + 1} 项【{item['name']}】的智能入口寻路失败。"
                        )
                        return

                    final_path_data.extend(path_data)
                    self._apply_state_side_effects_by_path(e_path)

                # 2. 智能宏入口：动态意图入口
                entry_intent = item.get("entry_intent")
                if entry_intent:
                    if not self.semantic_mapping:
                        messagebox.showerror(
                            "依赖缺失",
                            f"宏【{item['name']}】需要动态意图入口，但尚未提取意图映射。"
                        )
                        return

                    target_path_list = self.semantic_mapping.get(entry_intent)
                    if not target_path_list:
                        messagebox.showerror(
                            "宏入口适配失败",
                            f"当前机型 JSON 中未找到宏【{item['name']}】需要的入口：{entry_intent}"
                        )
                        return

                    e_path = tuple(target_path_list)

                    status, path_data = self.pathfinder.find_shortest_path(standby_path, e_path)
                    if status == "ERROR":
                        messagebox.showerror(
                            "宏入口动态寻路错误",
                            f"无法从待机状态自动路由至宏【{item['name']}】入口：{entry_intent}"
                        )
                        return

                    final_path_data.extend(path_data)
                    self._apply_state_side_effects_by_intent(entry_intent, e_path)

                # 3. 执行宏动作
                for act in item.get("actions", []):
                    final_path_data.append(
                        (act, ("MANUAL", f"宏包动作\n[{item['name']}]\n[{act}]"))
                    )

        if not final_path_data:
            messagebox.showinfo("提示", "当前队列无需产生任何按键动作。")
            return

        if self.visualizer_window is not None and self.visualizer_window.winfo_exists():
            self.visualizer_window.destroy()

        self.visualizer_window = PathVisualizer(
            self,
            start_state,
            final_path_data,
            vendor=current_vendor,
        )

    # ====== 数据库双端交互方法 ======
    def load_db_data(self):
        # 1. 加载复合指令 (Sequences)
        self.db_seq_listbox.delete(0, tk.END)
        self.cursor.execute("SELECT id, name FROM saved_sequences")
        for row in self.cursor.fetchall():
            self.db_seq_listbox.insert(tk.END, f"[{row[0]}] {row[1]}")

        # 2. 加载基础宏 (Macros)
        self.db_macro_listbox.delete(0, tk.END)
        self.macro_data_cache.clear()
        self.combo_macros.set('')
        self.cursor.execute("SELECT id, name, actions, entry_path, entry_intent FROM saved_macros")
        macro_names = []

        for row in self.fetchall_safe():
            db_id, name, actions_raw, entry_path_raw, entry_intent = row

            actions = json.loads(actions_raw) if actions_raw else []

            entry_path = None
            if entry_path_raw:
                try:
                    entry_path = tuple(json.loads(entry_path_raw))
                except Exception:
                    entry_path = None

            listbox_str = f"[{db_id}] {name}"
            if entry_path:
                listbox_str += "  🧭"
            elif entry_intent:
                listbox_str += "  🤖"

            self.db_macro_listbox.insert(tk.END, listbox_str)

            macro_names.append(name)
            self.macro_data_cache[name] = {
                "name": name,
                "actions": actions,
                "entry_path": entry_path,
                "entry_intent": entry_intent
            }

        self.combo_macros['values'] = macro_names
        self.load_api_settings_from_db()

    def fetchall_safe(self):
        try:
            return self.cursor.fetchall()
        except:
            return []

    def save_queue_as_macro(self):
        if not self.execution_queue:
            return

        entry_path = None
        entry_intent = None
        actions = []

        smart_entry_count = 0

        for item in self.execution_queue:
            if item["type"] == "path":
                smart_entry_count += 1
                entry_path = tuple(item["end"])
                entry_intent = None

            elif item["type"] == "intent":
                smart_entry_count += 1
                entry_intent = item["intent_key"]
                entry_path = None

            elif item["type"] == "action":
                actions.append(item["val"])

            elif item["type"] == "macro":
                # 嵌套宏：只继承动作，不继承它自己的入口，避免入口叠入口
                actions.extend(item.get("actions", []))

        if smart_entry_count > 1:
            messagebox.showerror(
                "不适合保存为基础宏",
                "基础宏最多只能包含一个智能寻路入口。\n"
                "当前队列包含多个寻路/动态意图，建议保存为【完整复合指令】。"
            )
            return

        if not actions:
            messagebox.showerror(
                "无法保存",
                "基础宏至少需要包含一个实际动作。\n"
                "如果只是多个路径切换，请保存为复合指令。"
            )
            return

        name = simpledialog.askstring("保存为智能基础宏", "请输入该宏的名称：")
        if not name:
            return

        actions_str = json.dumps(actions, ensure_ascii=False)

        entry_path_str = None
        if entry_path:
            entry_path_str = json.dumps(list(entry_path), ensure_ascii=False)

        self.cursor.execute(
            """
            INSERT INTO saved_macros 
            (name, actions, entry_path, entry_intent) 
            VALUES (?, ?, ?, ?)
            """,
            (name, actions_str, entry_path_str, entry_intent)
        )

        self.conn.commit()
        self.load_db_data()

        if entry_path or entry_intent:
            messagebox.showinfo("成功", "已保存为【智能基础宏】：包含自动寻路入口 + 盲按动作。")
        else:
            messagebox.showinfo("成功", "已保存为普通基础宏：仅包含盲按动作。")

    def save_queue_as_sequence(self):
        if not self.execution_queue: return
        name = simpledialog.askstring("保存复合指令", "请输入这套完整时间线指令的名称：")
        if not name: return

        seq_str = json.dumps(self.execution_queue)
        self.cursor.execute("INSERT INTO saved_sequences (name, sequence_json) VALUES (?, ?)", (name, seq_str))
        self.conn.commit()
        self.load_db_data()
        messagebox.showinfo("成功", "队列编排已保存到复合指令库！")

    def load_sequence_to_queue(self):
        sel = self.db_seq_listbox.curselection()
        if not sel: return
        item_text = self.db_seq_listbox.get(sel[0])
        db_id = int(item_text.split("]")[0].replace("[", ""))

        self.cursor.execute("SELECT sequence_json FROM saved_sequences WHERE id=?", (db_id,))
        row = self.cursor.fetchone()
        if row:
            raw_queue = json.loads(row[0])

            # 🚨 关键修复：将 JSON 解析出来的 list 强制还原为底层寻路所需的 tuple
            for item in raw_queue:
                if item["type"] == "path":
                    item["start"] = tuple(item["start"])
                    item["end"] = tuple(item["end"])

                elif item["type"] == "macro":
                    if item.get("entry_path"):
                        item["entry_path"] = tuple(item["entry_path"])

            self.execution_queue = raw_queue
            self.refresh_queue_ui()
            messagebox.showinfo("加载成功", "已将复合指令成功加载到执行队列，您可以直接运行或继续修改编排。")

    def delete_sequence(self):
        sel = self.db_seq_listbox.curselection()
        if not sel: return
        db_id = int(self.db_seq_listbox.get(sel[0]).split("]")[0].replace("[", ""))
        if messagebox.askyesno("确认", "确定删除这条复合指令吗？"):
            self.cursor.execute("DELETE FROM saved_sequences WHERE id=?", (db_id,))
            self.conn.commit()
            self.load_db_data()

    def delete_macro(self):
        sel = self.db_macro_listbox.curselection()
        if not sel: return
        db_id = int(self.db_macro_listbox.get(sel[0]).split("]")[0].replace("[", ""))
        if messagebox.askyesno("确认", "确定删除这个基础宏吗？\n注意：不会影响已经将它包含在内的复合指令。"):
            self.cursor.execute("DELETE FROM saved_macros WHERE id=?", (db_id,))
            self.conn.commit()
            self.load_db_data()

    # ====== 新增：全局文件与 LLM 控制逻辑 ======

    def _get_file_hash(self, filepath):
        """计算文件 MD5，用于精准判断是否为同一个 JSON 文件"""
        hasher = hashlib.md5()
        with open(filepath, 'rb') as f:
            buf = f.read()
            hasher.update(buf)
        return hasher.hexdigest()

    def load_json_file(self):
        filepath = filedialog.askopenfilename(title="选择 OSD JSON 文件", filetypes=[("JSON Files", "*.json")])
        if not filepath: return

        self.current_json_path = filepath
        self.current_json_hash = self._get_file_hash(filepath)
        self.lbl_file_path.config(text=os.path.basename(filepath), foreground="blue")

        # 1. 动态更新寻路器的核心数据
        self.pathfinder.update_data(filepath)

        # 2. 清空现有 UI 树形图并重新渲染
        for tree in (self.start_tree, self.end_tree):
            for item in tree.get_children():
                tree.delete(item)
        self.populate_trees()  # 重新调用现有的填充方法

        # 3. 重置大模型状态
        self.semantic_mapping = {}
        self.lbl_llm_status.config(text="等待解析", foreground="orange")
        self.log_message(f"✅ 成功加载新 JSON: {os.path.basename(filepath)}")

    def save_api_settings(self):
        key = self.api_key_var.get().strip()
        model = self.model_var.get().strip()
        if not key:
            messagebox.showwarning("警告", "API Key 不能为空！")
            return

        # 使用 REPLACE 实现存在即更新，不存在即插入
        self.cursor.execute("REPLACE INTO settings (key, value) VALUES ('api_key', ?)", (key,))
        self.cursor.execute("REPLACE INTO settings (key, value) VALUES ('model', ?)", (model,))
        self.conn.commit()
        self.log_message("💾 API 配置已保存到本地数据库。")
        messagebox.showinfo("成功", "配置保存成功！")

    def load_api_settings_from_db(self):
        """在 load_db_data 中顺便调用此方法加载配置"""
        self.cursor.execute("SELECT value FROM settings WHERE key='api_key'")
        res = self.cursor.fetchone()
        if res: self.api_key_var.set(res[0])

        self.cursor.execute("SELECT value FROM settings WHERE key='model'")
        res = self.cursor.fetchone()
        if res: self.model_var.set(res[0])

    def trigger_llm_scan(self):
        if not self.current_json_path:
            messagebox.showerror("错误", "请先载入 JSON 文件！")
            return

        api_key = self.api_key_var.get().strip()
        if not api_key:
            messagebox.showerror("错误", "请先填写并保存 NVIDIA API Key！")
            return

        # 1. 查缓存表，避免重复扣费
        self.cursor.execute("SELECT mapping_data FROM llm_cache WHERE json_hash=?", (self.current_json_hash,))
        cached_row = self.cursor.fetchone()

        if cached_row:
            self.semantic_mapping = json.loads(cached_row[0])
            self.lbl_llm_status.config(text="✅ 命中本地缓存，已就绪", foreground="green")
            self.log_message("⚡ 命中本地 LLM 缓存，直接加载成功！")
            return

        # 2. 无缓存，开始调用大模型
        self.log_message("🤖 正在请求 NVIDIA Qwen 接口进行语义解析，请稍候...")
        self.update()  # 刷新 UI 防止假死

        scanner = OSDSemanticScanner(api_key)
        scanner.model = self.model_var.get().strip()

        # 传入寻路器当前加载的树形字典
        result = scanner.scan_osd_menu(self.pathfinder.tree_data)

        if result:
            self.semantic_mapping = result
            # 存入数据库缓存
            self.cursor.execute("INSERT INTO llm_cache (json_hash, mapping_data) VALUES (?, ?)",
                                (self.current_json_hash, json.dumps(result)))
            self.conn.commit()

            self.lbl_llm_status.config(text="✅ LLM 解析成功并已缓存", foreground="green")
            self.log_message("🎉 语义解析完成并存入数据库！你可以随时调用意图快捷方式了。")
        else:
            self.lbl_llm_status.config(text="❌ 解析失败", foreground="red")
            self.log_message("❌ LLM 解析失败，请检查 API 密钥或网络。")

    def infer_picture_mode_from_path(self, path_tuple):
        """
        从绝对寻路目标判断是否改变了 Picture Mode。
        """
        if not path_tuple:
            return None

        picture_modes = {
            "Standard", "FPS", "MOBA", "RPG", "Racing", "Movie",
            "Reader", "ECO", "sRGB", "Adobe RGB", "DCI-P3", "Custom",
            "HDR", "HDR Game", "HDR Movie", "HDR Vivid", "HDR Peak1500"
        }

        last = path_tuple[-1]
        if last not in picture_modes:
            return None

        path_text = "/".join(path_tuple)

        # 兼容两个入口：
        # 1. Elite Menu(Picture Mode)
        # 2. Main Menu > Picture ( SDR 時) > Preset Mode
        if "Picture Mode" in path_text or "Preset Mode" in path_text:
            return last

        return None

    def is_reset_path(self, path_tuple):
        """
        判断是否为重置类路径。
        Reset All / Reset to default 后，Picture Mode 回 ECO。
        """
        if not path_tuple:
            return False

        path_text = "/".join(path_tuple).lower()

        reset_keywords = [
            "reset all",
            "reset to default",
            "reset settings",
            "reset picture"
        ]

        return any(key in path_text for key in reset_keywords)

    def infer_picture_mode_from_intent(self, intent_key):
        """
        从动态意图判断是否改变 Picture Mode。
        """
        mapping = {
            "INTENT_PICTURE_MODE_STANDARD": "Standard",
            "INTENT_PICTURE_MODE_SRGB": "sRGB",

            # 后续扩展
            # "INTENT_PICTURE_MODE_FPS": "FPS",
            # "INTENT_PICTURE_MODE_MOBA": "MOBA",
            # "INTENT_PICTURE_MODE_RPG": "RPG",
            # "INTENT_PICTURE_MODE_RACING": "Racing",
            # "INTENT_PICTURE_MODE_MOVIE": "Movie",
            # "INTENT_PICTURE_MODE_READER": "Reader",
            # "INTENT_PICTURE_MODE_ECO": "ECO",
        }

        return mapping.get(intent_key)


if __name__ == "__main__":
    app = App()
    app.mainloop()