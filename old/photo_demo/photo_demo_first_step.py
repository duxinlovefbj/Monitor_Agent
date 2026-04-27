import cv2
import tkinter as tk
import threading
import time
import os
from collections import deque
from datetime import datetime


class OSDCaptureDemo:
    def __init__(self):
        # --- 参数配置 ---
        self.camera_id = 0  # USB摄像头ID，根据实际情况修改
        self.width = 3840
        self.height = 2160
        self.fps_target = 10  # 目标帧率 (单张图片保存，不需要太高，10fps足够覆盖5秒变化)
        self.duration_half = 2.5  # 触发前/后各保存的时间 (秒)
        self.buffer_size = int(self.fps_target * self.duration_half)  # 环形缓存大小
        self.save_dir = "osd_captures"

        # --- 状态变量 ---
        self.frame_buffer = deque(maxlen=self.buffer_size)
        self.is_running = True
        self.is_recording = False
        self.frames_to_record = 0
        self.save_queue = []  # 用于暂存需要保存到硬盘的帧

        if not os.path.exists(self.save_dir):
            os.makedirs(self.save_dir)

        # --- 初始化 UI (Tkinter) ---
        self.root = tk.Tk()
        self.root.attributes('-fullscreen', True)
        self.root.configure(background='black')
        self.root.bind('<Escape>', self.quit_app)  # 按 Esc 退出
        self.root.bind('<space>', self.trigger_capture)  # 按 空格 触发拍摄

        self.setup_ui()

        # --- 启动摄像头读取线程 ---
        self.cap_thread = threading.Thread(target=self.camera_loop, daemon=True)
        self.cap_thread.start()

    def setup_ui(self):
        """绘制左黑右白的全屏界面"""
        screen_w = self.root.winfo_screenwidth()
        screen_h = self.root.winfo_screenheight()

        canvas = tk.Canvas(self.root, width=screen_w, height=screen_h, highlightthickness=0)
        canvas.pack()

        # 左半边黑色 (Tkinter 默认背景，或显式绘制)
        canvas.create_rectangle(0, 0, screen_w // 2, screen_h, fill="black", outline="")
        # 右半边纯白
        canvas.create_rectangle(screen_w // 2, 0, screen_w, screen_h, fill="white", outline="")

        # 提示信息
        canvas.create_text(screen_w // 4, screen_h // 2, text="Press [SPACE] to Capture\nPress [ESC] to Exit",
                           fill="white", font=("Arial", 24), justify="center")

    def camera_loop(self):
        """后台摄像头读取与缓存管理"""
        cap = cv2.VideoCapture(self.camera_id)
        # 强制设置 4K 分辨率 (部分摄像头可能需要使用 MJPG 格式才能输出 4K)
        cap.set(cv2.CAP_PROP_FRAME_WIDTH, self.width)
        cap.set(cv2.CAP_PROP_FRAME_HEIGHT, self.height)
        # cap.set(cv2.CAP_PROP_FOURCC, cv2.VideoWriter_fourcc(*'MJPG'))

        frame_delay = 1.0 / self.fps_target

        while self.is_running:
            start_time = time.time()
            ret, frame = cap.read()

            if ret:
                # 无论是否触发，始终维护最近 2.5 秒的缓存
                self.frame_buffer.append(frame)

                # 如果处于触发录制状态，收集触发后的帧
                if self.is_recording:
                    self.save_queue.append(frame.copy())
                    self.frames_to_record -= 1

                    if self.frames_to_record <= 0:
                        self.is_recording = False
                        self.start_saving_thread()
            else:
                print("Warning: Failed to grab frame.")
                time.sleep(0.1)

            # 控制帧率，避免读取过快占用过多资源
            elapsed = time.time() - start_time
            if elapsed < frame_delay:
                time.sleep(frame_delay - elapsed)

        cap.release()

    def trigger_capture(self, event=None):
        """按下空格键时的触发逻辑"""
        if self.is_recording:
            print("Already recording, please wait...")
            return

        print("Capture triggered! Gathering history frames...")
        # 1. 拷贝当前缓存中的历史帧 (触发前 2.5 秒)
        self.save_queue = list(self.frame_buffer)

        # 2. 设置需要继续收集的帧数 (触发后 2.5 秒)
        self.frames_to_record = self.buffer_size
        self.is_recording = True

    def start_saving_thread(self):
        """启动独立的存图线程，避免阻塞摄像头读取"""
        frames_to_save = self.save_queue.copy()
        self.save_queue.clear()

        save_thread = threading.Thread(target=self.save_frames_to_disk, args=(frames_to_save,))
        save_thread.start()

    def save_frames_to_disk(self, frames):
        """将收集到的所有帧写入硬盘"""
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        folder_path = os.path.join(self.save_dir, timestamp)
        os.makedirs(folder_path, exist_ok=True)

        print(f"Start saving {len(frames)} frames to {folder_path}...")

        for i, frame in enumerate(frames):
            # 命名格式: 001.jpg, 002.jpg ...
            filename = os.path.join(folder_path, f"{i:03d}.jpg")
            # 4K保存较慢，可根据需要调整 JPEG 质量参数以提升速度
            cv2.imwrite(filename, frame, [int(cv2.IMWRITE_JPEG_QUALITY), 90])

        print(f"Finished saving. Ready for next capture.")

    def quit_app(self, event=None):
        """安全退出程序"""
        print("Exiting...")
        self.is_running = False
        self.root.quit()


if __name__ == "__main__":
    app = OSDCaptureDemo()
    app.root.mainloop()