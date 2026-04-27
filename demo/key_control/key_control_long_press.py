import ctypes
import time
import threading
import tkinter as tk

# ================= 底层 USB 控制逻辑 =================
try:
    libusb = ctypes.CDLL('./libusb-1.0.dll')
except OSError as e:
    print(f"无法加载 libusb-1.0.dll，请确保它与本脚本在同一目录！\n错误信息: {e}")
    exit(1)

# 严谨声明所有被调用的 C 语言接口
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
    @staticmethod
    def send_usb_control_command(data_array):
        libusb.libusb_init(None)

        dev_handle = libusb.libusb_open_device_with_vid_pid(None, VID, PID)
        if not dev_handle:
            print("错误：未找到设备 (VID:0x5131, PID:0x2007) 或设备被占用。")
            libusb.libusb_exit(None)
            return False

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

    @staticmethod
    def _execute_action(action_tuple, manufacturer, duration):
        """
        执行按键动作
        :param duration: 按下持续时间（秒）
        """
        standby_tuple = (1, 1, 0, 0, 0)

        if manufacturer == "TPV":
            full_command = action_tuple + standby_tuple
        else:
            full_command = standby_tuple + action_tuple

        # 发送按下指令
        MonitorKeyController.send_usb_control_command(full_command)
        # 根据参数决定持续时间
        time.sleep(duration)
        # 发送全局复位（释放）指令
        MonitorKeyController.send_usb_control_command(standby_tuple + standby_tuple)

    @classmethod
    def trigger_action(cls, direction, manufacturer, duration=0.2):
        """
        触发按键动作入口
        :param duration: 默认 0.2s，长按规则可传入 2.0s
        """
        patterns = {
            "center": (0, 0, 0, 1, 1),
            "left": (0, 0, 1, 0, 1),
            "right": (0, 0, 0, 0, 1),
            "up": (0, 0, 1, 1, 0),
            "down": (0, 0, 1, 1, 1)
        }
        # 开启守护线程执行，防止阻塞 GUI
        threading.Thread(
            target=cls._execute_action,
            args=(patterns[direction], manufacturer, duration),
            daemon=True
        ).start()


# ================= GUI 界面 =================
def create_gui():
    root = tk.Tk()
    root.title("显示器控制板 (Pro)")

    window_width = 320
    window_height = 360  # 稍微调高以容纳长按按钮
    screen_width = root.winfo_screenwidth()
    screen_height = root.winfo_screenheight()
    x = (screen_width - window_width) // 2
    y = (screen_height - window_height) // 2
    root.geometry(f"{window_width}x{window_height}+{x}+{y}")
    root.resizable(False, False)

    manufacturer_var = tk.StringVar(value="KTC")
    frame_vendor = tk.LabelFrame(root, text=" 选择厂商通道 ", font=('微软雅黑', 10))
    frame_vendor.place(x=20, y=10, width=280, height=60)

    tk.Radiobutton(frame_vendor, text="TPV & MOKA", variable=manufacturer_var, value="TPV").place(x=15, y=5)
    tk.Radiobutton(frame_vendor, text="KTC", variable=manufacturer_var, value="KTC").place(x=160, y=5)

    btn_config = {'width': 6, 'height': 2, 'font': ('微软雅黑', 11, 'bold'), 'bg': '#e0e0e0'}

    # 修改动作触发包裹函数，支持传入 duration
    def do_action(dir_key, duration=0.2):
        MonitorKeyController.trigger_action(dir_key, manufacturer_var.get(), duration)

    # 标准方向键
    tk.Button(root, text="上 键", command=lambda: do_action("up"), **btn_config).place(x=125, y=90)
    tk.Button(root, text="左 键", command=lambda: do_action("left"), **btn_config).place(x=50, y=160)
    tk.Button(root, text="中 键", command=lambda: do_action("center"), **btn_config).place(x=125, y=160)
    tk.Button(root, text="右 键", command=lambda: do_action("right"), **btn_config).place(x=200, y=160)
    tk.Button(root, text="下 键", command=lambda: do_action("down"), **btn_config).place(x=125, y=230)

    # --- 新增：长按规则按钮 ---
    # 针对中键增加一个显式的“长按 2s”功能按钮
    btn_long_press = tk.Button(
        root,
        text="中键 (长按 2s)",
        command=lambda: do_action("center", 2.0),
        width=16, height=1,
        font=('微软雅黑', 10, 'bold'),
        bg='#ffcc80',  # 使用橙色区分功能
        activebackground='#ffa726'
    )
    btn_long_press.place(x=85, y=305)

    root.mainloop()


if __name__ == "__main__":
    create_gui()