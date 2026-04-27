import ctypes
import threading
import tkinter as tk

# ================= 底层 USB 控制逻辑 =================
try:
    libusb = ctypes.CDLL('libusb-1.0.dll')
except OSError as e:
    print(f"无法加载 libusb-1.0.dll，请确保它与本脚本在同一目录！\n错误信息: {e}")
    exit(1)

# 严谨声明所有被调用的 C 语言接口的 参数类型(argtypes) 和 返回值类型(restype)
libusb.libusb_init.argtypes = [ctypes.c_void_p]
libusb.libusb_init.restype = ctypes.c_int
libusb.libusb_open_device_with_vid_pid.argtypes = [ctypes.c_void_p, ctypes.c_uint16, ctypes.c_uint16]
libusb.libusb_open_device_with_vid_pid.restype = ctypes.c_void_p
libusb.libusb_claim_interface.argtypes = [ctypes.c_void_p, ctypes.c_int]
libusb.libusb_claim_interface.restype = ctypes.c_int
libusb.libusb_detach_kernel_driver.argtypes = [ctypes.c_void_p, ctypes.c_int]
libusb.libusb_detach_kernel_driver.restype = ctypes.c_int
libusb.libusb_bulk_transfer.argtypes = [
    ctypes.c_void_p, ctypes.c_ubyte, ctypes.c_void_p, ctypes.c_int, ctypes.POINTER(ctypes.c_int), ctypes.c_uint
]
libusb.libusb_bulk_transfer.restype = ctypes.c_int
libusb.libusb_release_interface.argtypes = [ctypes.c_void_p, ctypes.c_int]
libusb.libusb_release_interface.restype = ctypes.c_int
libusb.libusb_close.argtypes = [ctypes.c_void_p]
libusb.libusb_exit.argtypes = [ctypes.c_void_p]

VID = 0x5131
PID = 0x2007
OUT_ENDPOINT = 0x02
DATA_LENGTH = 64
TIMEOUT = 1000


class MonitorKeyController:
    # 增加类级线程锁，防止快速按下/松开引发的底层 USB 竞争崩溃
    _usb_lock = threading.Lock()

    @classmethod
    def send_usb_control_command(cls, data_array):
        with cls._usb_lock:
            libusb.libusb_init(None)

            dev_handle = libusb.libusb_open_device_with_vid_pid(None, VID, PID)
            if not dev_handle:
                print("错误：未找到设备 (VID:0x5131, PID:0x2007) 或设备被占用。")
                libusb.libusb_exit(None)
                return False

            # 构造 64 字节的数据
            data = (ctypes.c_ubyte * DATA_LENGTH)()
            data[0] = 0x00
            for i in range(10):
                data[i + 1] = data_array[i]

            res = libusb.libusb_claim_interface(dev_handle, 0)
            if res < 0:
                libusb.libusb_detach_kernel_driver(dev_handle, 0)
                res = libusb.libusb_claim_interface(dev_handle, 0)

            success = False
            if res >= 0:
                transferred = ctypes.c_int(0)
                transfer_res = libusb.libusb_bulk_transfer(
                    dev_handle, OUT_ENDPOINT, ctypes.cast(data, ctypes.c_void_p),
                    DATA_LENGTH, ctypes.byref(transferred), TIMEOUT
                )

                if transfer_res == 0:
                    print(f"指令发送成功，共写入 {transferred.value} 字节")
                    success = True
                else:
                    print(f"指令发送失败，错误码: {transfer_res}")

                libusb.libusb_release_interface(dev_handle, 0)

            libusb.libusb_close(dev_handle)
            libusb.libusb_exit(None)
            return success

    @classmethod
    def _get_mapped_pattern(cls, direction, manufacturer):
        # 以 KTC 为基准的标准动作电平
        patterns = {
            "center": (0, 0, 0, 1, 1),
            "left": (0, 0, 1, 0, 1),
            "right": (0, 0, 0, 0, 1),
            "up": (0, 0, 1, 1, 0),
            "down": (0, 0, 1, 1, 1)
        }

        # 针对 TPV 厂商，互换“上”和“右”
        if manufacturer == "TPV":
            if direction == "up":
                return patterns["right"]
            elif direction == "right":
                return patterns["up"]

        return patterns[direction]

    @classmethod
    def press_action(cls, direction, manufacturer):
        action_tuple = cls._get_mapped_pattern(direction, manufacturer)
        standby_tuple = (1, 1, 0, 0, 0)

        # 组装完整的 10 字节指令阵列
        if manufacturer == "TPV":
            full_command = action_tuple + standby_tuple
        else:
            full_command = standby_tuple + action_tuple

        # 发送按下指令
        threading.Thread(target=cls.send_usb_control_command, args=(full_command,), daemon=True).start()

    @classmethod
    def release_action(cls):
        standby_tuple = (1, 1, 0, 0, 0)
        # 组装全局复位/待机指令
        full_command = standby_tuple + standby_tuple

        # 发送松开指令
        threading.Thread(target=cls.send_usb_control_command, args=(full_command,), daemon=True).start()


# ================= GUI 界面 =================
def create_gui():
    root = tk.Tk()
    root.title("显示器控制板")

    window_width = 300
    window_height = 290
    screen_width = root.winfo_screenwidth()
    screen_height = root.winfo_screenheight()
    x = (screen_width - window_width) // 2
    y = (screen_height - window_height) // 2
    root.geometry(f"{window_width}x{window_height}+{x}+{y}")
    root.resizable(False, False)

    # 厂商选择区域
    manufacturer_var = tk.StringVar(value="TPV")
    frame_vendor = tk.LabelFrame(root, text=" 选择厂商通道 ", font=('微软雅黑', 10))
    frame_vendor.place(x=20, y=10, width=260, height=60)

    tk.Radiobutton(frame_vendor, text="TPV & MOKA", variable=manufacturer_var, value="TPV").place(x=15, y=5)
    tk.Radiobutton(frame_vendor, text="KTC", variable=manufacturer_var, value="KTC").place(x=150, y=5)

    btn_config = {'width': 6, 'height': 2, 'font': ('微软雅黑', 11, 'bold'), 'bg': '#e0e0e0'}

    # 将原有 command 逻辑替换为事件绑定机制
    def bind_button_events(button_widget, direction_key):
        button_widget.bind("<ButtonPress-1>",
                           lambda e: MonitorKeyController.press_action(direction_key, manufacturer_var.get()))
        button_widget.bind("<ButtonRelease-1>", lambda e: MonitorKeyController.release_action())

    btn_up = tk.Button(root, text="上 键", **btn_config)
    btn_up.place(x=115, y=90)
    bind_button_events(btn_up, "up")

    btn_left = tk.Button(root, text="左 键", **btn_config)
    btn_left.place(x=40, y=160)
    bind_button_events(btn_left, "left")

    btn_center = tk.Button(root, text="中 键", **btn_config)
    btn_center.place(x=115, y=160)
    bind_button_events(btn_center, "center")

    btn_right = tk.Button(root, text="右 键", **btn_config)
    btn_right.place(x=190, y=160)
    bind_button_events(btn_right, "right")

    btn_down = tk.Button(root, text="下 键", **btn_config)
    btn_down.place(x=115, y=230)
    bind_button_events(btn_down, "down")

    root.mainloop()


if __name__ == "__main__":
    create_gui()