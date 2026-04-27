import ctypes
import threading
import time

# ==========================================
# 硬件控制模块
# ==========================================
class MonitorController:
    _VID = 0x5131
    _PID = 0x2007
    _OUT_ENDPOINT = 0x02
    _DATA_LENGTH = 64
    _TIMEOUT = 1000

    # 增加线程锁，防止并发操作 USB 导致崩溃
    _usb_lock = threading.Lock()

    _PATTERNS = {
        "center": (0, 0, 0, 1, 1),
        "left": (0, 0, 1, 0, 1),
        "right": (0, 0, 0, 0, 1),
        "up": (0, 0, 1, 1, 0),
        "down": (0, 0, 1, 1, 1),
        "standby": (1, 1, 0, 0, 0)
    }

    _libusb = None

    @classmethod
    def _init_usb_library(cls):
        if cls._libusb is not None: return True
        try:
            cls._libusb = ctypes.CDLL('./libusb-1.0.dll')
            cls._libusb.libusb_init.argtypes = [ctypes.c_void_p]
            cls._libusb.libusb_init.restype = ctypes.c_int
            cls._libusb.libusb_open_device_with_vid_pid.argtypes = [ctypes.c_void_p, ctypes.c_uint16, ctypes.c_uint16]
            cls._libusb.libusb_open_device_with_vid_pid.restype = ctypes.c_void_p
            cls._libusb.libusb_claim_interface.argtypes = [ctypes.c_void_p, ctypes.c_int]
            cls._libusb.libusb_claim_interface.restype = ctypes.c_int
            cls._libusb.libusb_detach_kernel_driver.argtypes = [ctypes.c_void_p, ctypes.c_int]
            cls._libusb.libusb_detach_kernel_driver.restype = ctypes.c_int
            cls._libusb.libusb_bulk_transfer.argtypes = [
                ctypes.c_void_p, ctypes.c_ubyte, ctypes.c_void_p, ctypes.c_int,
                ctypes.POINTER(ctypes.c_int), ctypes.c_uint
            ]
            cls._libusb.libusb_bulk_transfer.restype = ctypes.c_int
            cls._libusb.libusb_release_interface.argtypes = [ctypes.c_void_p, ctypes.c_int]
            cls._libusb.libusb_release_interface.restype = ctypes.c_int
            cls._libusb.libusb_close.argtypes = [ctypes.c_void_p]
            cls._libusb.libusb_exit.argtypes = [ctypes.c_void_p]
            return True
        except OSError:
            return False

    @classmethod
    def _get_mapped_pattern(cls, direction, manufacturer):
        """核心逻辑：根据厂商处理方向映射"""
        if manufacturer.upper() == "TPV":
            if direction == "up": return cls._PATTERNS["right"]
            if direction == "right": return cls._PATTERNS["up"]
        return cls._PATTERNS.get(direction)

    @classmethod
    def _raw_send(cls, data_array):
        """核心逻辑：使用锁保护的底层发送"""
        if not cls._init_usb_library(): return False

        with cls._usb_lock:
            cls._libusb.libusb_init(None)
            handle = cls._libusb.libusb_open_device_with_vid_pid(None, cls._VID, cls._PID)
            if not handle:
                cls._libusb.libusb_exit(None)
                return False

            buf = (ctypes.c_ubyte * cls._DATA_LENGTH)()
            buf[0] = 0x00
            # 填充前 10 字节数据
            for i in range(min(len(data_array), 10)):
                buf[i + 1] = data_array[i]

            success = False
            res = cls._libusb.libusb_claim_interface(handle, 0)
            if res < 0:
                cls._libusb.libusb_detach_kernel_driver(handle, 0)
                res = cls._libusb.libusb_claim_interface(handle, 0)

            if res >= 0:
                transferred = ctypes.c_int(0)
                cls._libusb.libusb_bulk_transfer(
                    handle, cls._OUT_ENDPOINT, ctypes.cast(buf, ctypes.c_void_p),
                    cls._DATA_LENGTH, ctypes.byref(transferred), cls._TIMEOUT
                )
                success = True
                cls._libusb.libusb_release_interface(handle, 0)

            cls._libusb.libusb_close(handle)
            cls._libusb.libusb_exit(None)
            return success

    @classmethod
    def _execute_sequence(cls, direction, manufacturer, duration=0.2):
        """核心逻辑：根据厂商处理字节序组合"""
        action_tuple = cls._get_mapped_pattern(direction, manufacturer)
        standby_tuple = cls._PATTERNS["standby"]
        if not action_tuple: return

        # TPV: 动作在前，待机在后； KTC: 待机在前，动作在后
        if manufacturer.upper() == "TPV":
            full_command = action_tuple + standby_tuple
        else:
            full_command = standby_tuple + action_tuple

        # 发送按下指令
        cls._raw_send(full_command)
        time.sleep(duration)
        # 发送松开指令 (双待机)
        cls._raw_send(standby_tuple + standby_tuple)

    @classmethod
    def press(cls, action_name, manufacturer="KTC", async_mode=True):
        """动态解析按键名称与按压时长"""
        # 1. 基础方向映射
        direction_map = {
            "上键": "up", "下键": "down",
            "左键": "left", "右键": "right",
            "中键": "center"
        }

        # 2. 剥离“长按”前缀，获取真实键名
        is_long_press = action_name.startswith("长按")
        key_name = action_name.replace("长按", "") if is_long_press else action_name

        # 如果不是标准物理按键（例如"休眠5s"、"测试画面"），直接拦截，不走 USB 硬件发送
        if key_name not in direction_map:
            return

        direction = direction_map[key_name]

        # 3. 动态分配时长逻辑
        if is_long_press:
            # 针对不同按键赋予不同的长按阈值 (调节数值往往需要更久)
            if key_name in ["上键", "下键", "左键", "右键"]:
                duration = 12.0  # 调节刻度类长按 12 秒
            else:
                duration = 2.0  # 中键长按开关机 2 秒
        else:
            duration = 0.2  # 标准短按

        # 4. 执行发送
        if async_mode:
            threading.Thread(target=cls._execute_sequence, args=(direction, manufacturer, duration),
                             daemon=True).start()
        else:
            cls._execute_sequence(direction, manufacturer, duration)

