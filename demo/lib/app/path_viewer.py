import tkinter as tk
from demo.lib.actions.displayhdr import DisplayHDRController
from demo.lib.actions.pattern import ScreenPatternTester
from demo.lib.ca410.ca410_control import CA410Controller
from demo.lib.control.key_control import MonitorController
# ==========================================
# 可视化与动画展示 (保留原逻辑)
# ==========================================
class PathVisualizer(tk.Toplevel):
    def __init__(self, parent, start_state, path_data, vendor="KTC", measure_callback=None):
        super().__init__(parent)
        self.vendor = vendor
        self.measure_callback = measure_callback

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
        self.after(800, self.animate_step)

    def round_rect(self, x1, y1, x2, y2, radius=15, **kwargs):
        points = [x1 + radius, y1, x2 - radius, y1, x2, y1, x2, y1 + radius, x2, y2 - radius, x2, y2,
                  x2 - radius, y2, x1 + radius, y2, x1, y2, x1, y2 - radius, x1, y1 + radius, x1, y1]
        return self.canvas.create_polygon(points, **kwargs, smooth=True)

    def draw_dpad(self):
        cx, cy, w, h, gap = 700, 300, 60, 60, 5
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
        self.dpad_ids["长按上键"] = self.dpad_ids["上键"]
        self.dpad_ids["长按下键"] = self.dpad_ids["下键"]

        self.canvas.create_text(cx, cy - h - gap, text="UP", fill="white", font=("Arial", 12, "bold"))
        self.canvas.create_text(cx, cy + h + gap, text="DOWN", fill="white", font=("Arial", 12, "bold"))
        self.canvas.create_text(cx - w - gap, cy, text="LEFT", fill="white", font=("Arial", 12, "bold"))
        self.canvas.create_text(cx + w + gap, cy, text="RIGHT", fill="white", font=("Arial", 12, "bold"))
        self.canvas.create_text(cx, cy, text="OK", fill="white", font=("Arial", 12, "bold"))

    def state_to_text(self, state):
        if state[0] == "MANUAL": return state[1]
        if state[0] == "IDLE":
            return "待机 / 黑屏"
        elif state[0] == "MAIN_MENU":
            return "主菜单快捷圈"
        else:
            menu_path, item = state[1], state[2]
            parent_name = menu_path[-1] if menu_path else "Root"
            return f"[{parent_name}]\n➔ {item}"

    def draw_node(self, text, x, y, is_start=False):
        w, h = 180, 50
        bg_color = "#ff9800" if is_start else "#00bcd4"
        if "宏" in text or "动作" in text: bg_color = "#9C27B0"
        self.round_rect(x, y, x + w, y + h, radius=10, fill=bg_color, outline="white", width=2)
        self.canvas.create_text(x + w / 2, y + h / 2, text=text, fill="white", font=("Microsoft YaHei", 10, "bold"),
                                justify="center")

    def animate_step(self):
        if self.step_index >= len(self.path_data):
            self.canvas.create_text(400, self.curr_y + 100, text="✅ 队列演示与硬件操作完毕！", fill="#4CAF50",
                                    font=("Microsoft YaHei", 16, "bold"))
            return

        action, next_state = self.path_data[self.step_index]
        btn_id = self.dpad_ids.get(action)

        # --- 关键修改：提前计算下一个节点的坐标 ---
        next_x, next_y = self.curr_x, self.curr_y + 80
        if next_y > 500:
            next_y = 50
            next_x += 220
        # ---------------------------------------

        if action.startswith("休眠"):
            # 动态提取休眠秒数 (例如从 "休眠10s" 提取出 10)
            try:
                sleep_sec = int(action.replace("休眠", "").replace("s", ""))
            except ValueError:
                sleep_sec = 5  # 兜底容错

            next_step_delay = sleep_sec * 1000
            self.master.log_message(f"💤 执行指令: 挂起休眠 {sleep_sec} 秒...")


        elif action.startswith("测试画面"):
            pattern_type = action.split("(")[1].split(")")[0]
            if pattern_type == "32阶Gamma":
                # 🚨 特殊处理：启动 32 阶异步量测流程
                # 因为这个流程非常长，我们直接通过一个独立方法处理，执行完后再回来
                self.master.log_message("📊 启动 32 阶 Gamma 自动化采集序列...")
                self._execute_gamma_33_steps()
                next_step_delay = 500  # 启动延迟

            elif pattern_type == "DisplayHDR":
                # 启动外部软件
                DisplayHDRController.launch()
                self.master.log_message("🖥️ 启动 DisplayHDR Compliance Test 软件")
                next_step_delay = 3000

            else:
                # 常规 RGB 纯色切换
                color_map = {
                    "Red": "#FF0000", "Green": "#00FF00", "Blue": "#0000FF",
                    "White": "#FFFFFF", "Black": "#000000"
                }
                hex_color = color_map.get(pattern_type, "#FFFFFF")
                ScreenPatternTester.show(hex_color, parent=self)
                self.master.log_message(f"🎨 渲染全屏 Pattern: {pattern_type}")
                next_step_delay = 1500  # 给面板和探头留出 1.5s 稳定时间

        elif action == "测量亮度":
            # 完整获取探头返回的所有数据字段，字典格式
            full_data = CA410Controller.measure_and_get_data(
                zero_cal_before_measure=True
            )
            if full_data:
                # 1. 打印完整原始数据
                self.master.log_message(f"📊 单次量测完整数据: {full_data}")
                # 2. 写入 CSV，带上下文、自动清洗 -99999999
                if hasattr(self.master, "save_ca410_measurement_to_csv"):
                    self.master.save_ca410_measurement_to_csv(
                        full_data,
                        action_name=action,
                        queue_display=str(next_state),
                        source_type="PathVisualizer",
                        source_name="执行队列"
                    )
                # 3. UI 动画展示 Lv
                lv = full_data.get("lv", 0)

                try:
                    lv_text = f"Lv:{float(lv):.1f}"

                except Exception:
                    lv_text = f"Lv:{lv}"

                self.canvas.create_text(
                    next_x + 90,
                    next_y + 70,
                    text=lv_text,
                    fill="#FFEB3B",
                    font=("Arial", 10, "bold")
                )

            else:
                self.master.log_message("❌ 测量失败，未获取到数据。")
            next_step_delay = 2500

        elif action == "切换系统HDR":
            # 模拟 Windows 快捷键 Win + Alt + B
            import pyautogui
            pyautogui.hotkey('win', 'alt', 'b')
            self.master.log_message("⚡ 模拟快捷键 Win+Alt+B 切换系统 HDR 状态")
            next_step_delay = 7000  # HDR 模式切换伴随显示器重连，建议给 7 秒

        else:
            # 物理按键派发给硬件模块
            MonitorController.press(action, manufacturer=self.vendor, async_mode=True)
            self.master.log_message(f"🔘 发送按键: {action}")

            # 计算下一个指令的间隔延迟
            if action.startswith("长按"):
                if "中键" in action:
                    next_step_delay = 2500  # 中键 2秒 + 缓冲
                else:
                    next_step_delay = 12500  # 方向键 12秒 + 缓冲
            else:
                next_step_delay = 1500  # 短按间隔

            # 如果 UI 上有对应按钮的高亮逻辑，可以保留
        if btn_id: self.canvas.itemconfig(btn_id, fill="#4CAF50")

        # 原本在这里的 next_x, next_y 计算代码已经被删掉/移动到了上方

        def show_next_node():
            if btn_id: self.canvas.itemconfig(btn_id, fill="#555555")
            if next_x == self.curr_x:
                self.canvas.create_line(self.curr_x + 90, self.curr_y + 50, next_x + 90, next_y, arrow=tk.LAST,
                                        fill="white", width=2)
            else:
                self.canvas.create_line(self.curr_x + 180, self.curr_y + 25, next_x, next_y + 25, arrow=tk.LAST,
                                        fill="white", width=2)
            self.draw_node(self.state_to_text(next_state), next_x, next_y)
            self.curr_x, self.curr_y = next_x, next_y
            self.step_index += 1
            self.after(next_step_delay, self.animate_step)

        self.after(300, show_next_node)

    def _execute_gamma_33_steps(self, current_step=0, results_list=None):
        """
        内部方法：执行 33 阶 Gamma 测量，并收集完整数据
        标准灰阶：
        0, 7, 15, 23, ... , 247, 255
        """

        gamma_gray_levels = [
            0,
            7, 15, 23, 31, 39, 47, 55, 63,
            71, 79, 87, 95, 103, 111, 119, 127,
            135, 143, 151, 159, 167, 175, 183, 191,
            199, 207, 215, 223, 231, 239, 247, 255
        ]

        total_steps = len(gamma_gray_levels)

        # 第一次调用时初始化空列表
        if results_list is None:
            results_list = []

        # 全部测完
        if current_step >= total_steps:
            self.master.log_message("🎉 33 阶 Gamma 采集完毕，正在关闭渲染窗口...")
            ScreenPatternTester.close()

            self.master.log_message(
                f"📦 完整 Gamma 数据集获取成功，共 {len(results_list)} 条记录！"
            )

            if results_list:
                print(f"Gamma 阶数 1 的完整数据: {results_list[0]}")
                print(f"Gamma 阶数 {total_steps} 的完整数据: {results_list[-1]}")

            # TODO: 在这里预留接口，例如将 results_list 传递给 Excel 导出模块
            # ExportModule.save_to_excel(results_list, "gamma_report.xlsx")
            return

        # 1. 使用标准 33 阶灰阶值
        level = gamma_gray_levels[current_step]
        hex_color = ScreenPatternTester.rgb_to_hex(level, level, level)

        # 2. 渲染画面
        ScreenPatternTester.show(hex_color, parent=self)

        # 3. 等待面板和探头稳定后测量
        def _measure_task():
            full_data = CA410Controller.measure_and_get_data(
                zero_cal_before_measure=False
            )

            if full_data:
                # 兼容 lv / Lv 字段名
                if 'lv' in full_data and 'Lv' not in full_data:
                    full_data['Lv'] = full_data['lv']

                # 补充测试上下文
                full_data['Test_Step'] = current_step + 1
                full_data['Input_GrayLevel'] = level
                full_data['Total_Steps'] = total_steps

                results_list.append(full_data)

                y_val = full_data.get('Lv', 0)

                self.master.log_message(
                    f"  [Step {current_step + 1}/{total_steps}] "
                    f"Gray {level} -> 量测成功 (Lv: {y_val:.4f})"
                )
            else:
                self.master.log_message(
                    f"  [Step {current_step + 1}/{total_steps}] "
                    f"Gray {level} -> ❌ 量测失败"
                )

            # 4. 递归下一步
            self.after(
                500,
                lambda: self._execute_gamma_33_steps(
                    current_step + 1,
                    results_list
                )
            )

        self.after(1500, _measure_task)