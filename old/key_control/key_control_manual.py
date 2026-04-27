import ctypes
import time
import threading
import tkinter as tk

# ================= 底层 USB 控制逻辑 =================
try:
    libusb = ctypes.CDLL('libusb-1.0.dll')
except OSError as e:
    print(f"无法加载 libusb-1.0.dll，请确保它与本脚本在同一目录！\n错误信息: {e}")
    exit(1)

# 【核心修复】：严谨声明所有被调用的 C 语言接口的 参数类型(argtypes) 和 返回值类型(restype)
libusb.libusb_init.argtypes = [ctypes.c_void_p]
libusb.libusb_init.restype = ctypes.c_int

libusb.libusb_open_device_with_vid_pid.argtypes = [ctypes.c_void_p, ctypes.c_uint16, ctypes.c_uint16]
libusb.libusb_open_device_with_vid_pid.restype = ctypes.c_void_p  # 返回64位指针

libusb.libusb_claim_interface.argtypes = [ctypes.c_void_p, ctypes.c_int]
libusb.libusb_claim_interface.restype = ctypes.c_int

libusb.libusb_detach_kernel_driver.argtypes = [ctypes.c_void_p, ctypes.c_int]
libusb.libusb_detach_kernel_driver.restype = ctypes.c_int

libusb.libusb_bulk_transfer.argtypes = [
    ctypes.c_void_p,  # dev_handle
    ctypes.c_ubyte,  # endpoint
    ctypes.c_void_p,  # data
    ctypes.c_int,  # length
    ctypes.POINTER(ctypes.c_int),  # transferred
    ctypes.c_uint  # timeout
]
libusb.libusb_bulk_transfer.restype = ctypes.c_int

libusb.libusb_release_interface.argtypes = [ctypes.c_void_p, ctypes.c_int]
libusb.libusb_release_interface.restype = ctypes.c_int

libusb.libusb_close.argtypes = [ctypes.c_void_p]
libusb.libusb_exit.argtypes = [ctypes.c_void_p]

# 常量定义
VID = 0x5131
PID = 0x2007
OUT_ENDPOINT = 0x02
DATA_LENGTH = 64
TIMEOUT = 1000


class MonitorKeyController:
    @staticmethod
    def send_usb_control_command(xen, yen, sel0, sel1, sel2, xen2, yen2, sel00, sel11, sel22):
        libusb.libusb_init(None)

        dev_handle = libusb.libusb_open_device_with_vid_pid(None, VID, PID)
        if not dev_handle:
            print("错误：未找到设备 (VID:0x5131, PID:0x2007) 或设备被占用。")
            libusb.libusb_exit(None)
            return False

        # 构造 64 字节的数据
        data = (ctypes.c_ubyte * DATA_LENGTH)()
        data[0] = 0x00
        data[1] = xen
        data[2] = yen
        data[3] = sel0
        data[4] = sel1
        data[5] = sel2
        data[6] = xen2
        data[7] = yen2
        data[8] = sel00
        data[9] = sel11
        data[10] = sel22

        res = libusb.libusb_claim_interface(dev_handle, 0)
        if res < 0:
            libusb.libusb_detach_kernel_driver(dev_handle, 0)
            res = libusb.libusb_claim_interface(dev_handle, 0)

        success = False
        if res >= 0:
            transferred = ctypes.c_int(0)
            transfer_res = libusb.libusb_bulk_transfer(
                dev_handle,
                OUT_ENDPOINT,
                ctypes.cast(data, ctypes.c_void_p),
                DATA_LENGTH,
                ctypes.byref(transferred),
                TIMEOUT
            )

            if transfer_res == 0:
                print(f"指令发送成功，共写入 {transferred.value} 字节")
                success = True
            else:
                print(f"指令发送失败，错误码: {transfer_res}")

            libusb.libusb_release_interface(dev_handle, 0)
        else:
            print("无法抢占 USB 接口")

        libusb.libusb_close(dev_handle)
        libusb.libusb_exit(None)
        return success

    @staticmethod
    def release_key():
        MonitorKeyController.send_usb_control_command(1, 1, 0, 0, 0, 1, 1, 0, 0, 0)

    @staticmethod
    def _execute_action(xen, yen, sel0, sel1, sel2, xen2, yen2, sel00, sel11, sel22):
        MonitorKeyController.send_usb_control_command(xen, yen, sel0, sel1, sel2, xen2, yen2, sel00, sel11, sel22)
        time.sleep(0.2)
        MonitorKeyController.release_key()

    @classmethod
    def trigger_action(cls, *args):
        threading.Thread(target=cls._execute_action, args=args, daemon=True).start()

    @classmethod
    def up(cls):
        cls.trigger_action(0, 0, 0, 1, 1, 1, 1, 0, 0, 0)

    @classmethod
    def down(cls):
        cls.trigger_action(0, 0, 1, 0, 1, 1, 1, 0, 0, 0)

    @classmethod
    def left(cls):
        cls.trigger_action(0, 0, 0, 0, 1, 1, 1, 0, 0, 0)

    @classmethod
    def right(cls):
        cls.trigger_action(0, 0, 1, 1, 0, 1, 1, 0, 0, 0)

    @classmethod
    def center(cls):
        cls.trigger_action(0, 0, 1, 1, 1, 1, 1, 0, 0, 0)


# ================= GUI 界面 =================
def create_gui():
    root = tk.Tk()
    root.title("显示器按键控制")

    window_width = 280
    window_height = 240
    screen_width = root.winfo_screenwidth()
    screen_height = root.winfo_screenheight()
    x = (screen_width - window_width) // 2
    y = (screen_height - window_height) // 2
    root.geometry(f"{window_width}x{window_height}+{x}+{y}")
    root.resizable(False, False)

    btn_config = {'width': 6, 'height': 2, 'font': ('微软雅黑', 11, 'bold'), 'bg': '#e0e0e0'}

    btn_up = tk.Button(root, text="上 键", command=MonitorKeyController.up, **btn_config)
    btn_up.place(x=105, y=20)

    btn_left = tk.Button(root, text="左 键", command=MonitorKeyController.left, **btn_config)
    btn_left.place(x=30, y=90)

    btn_center = tk.Button(root, text="中 键", command=MonitorKeyController.center, **btn_config)
    btn_center.place(x=105, y=90)

    btn_right = tk.Button(root, text="右 键", command=MonitorKeyController.right, **btn_config)
    btn_right.place(x=180, y=90)

    btn_down = tk.Button(root, text="下 键", command=MonitorKeyController.down, **btn_config)
    btn_down.place(x=105, y=160)

    root.mainloop()


if __name__ == "__main__":
    create_gui()