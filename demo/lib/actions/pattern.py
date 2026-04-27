import tkinter as tk

class ScreenPatternTester:
    """
    通用全屏纯色/灰阶测试模块 (单例模式)
    """
    _win = None

    @classmethod
    def show(cls, color_hex="#FFFFFF", parent=None):
        """
        显示或更新全屏颜色
        :param color_hex: 颜色的 Hex 字符串，如 "#FF0000" (红), "#808080" (灰)
        :param parent: 父窗口句柄（如果在 GUI 中运行）
        """
        # 如果窗口不存在，则初始化
        if cls._win is None or not cls._win.winfo_exists():
            is_standalone = False
            if parent is None:
                cls._win = tk.Tk()
                is_standalone = True
            else:
                cls._win = tk.Toplevel(parent)

            cls._win.attributes("-fullscreen", True)
            cls._win.attributes("-topmost", True)
            cls._win.configure(cursor="none")
            cls._win.title("Pattern Test")

            def _close(event):
                cls.close()
                if is_standalone:
                    # 仅在独立运行时退出主循环
                    import sys
                    sys.exit(0)

            cls._win.bind("<Escape>", _close)

        # 更新背景颜色并强制刷新
        cls._win.configure(bg=color_hex)
        cls._win.update()

    @classmethod
    def close(cls):
        """关闭全屏测试窗口"""
        if cls._win and cls._win.winfo_exists():
            cls._win.destroy()
            cls._win = None

    @staticmethod
    def rgb_to_hex(r, g, b):
        """辅助方法：将 RGB (0-255) 转换为 Hex 字符串"""
        return f"#{int(r):02X}{int(g):02X}{int(b):02X}"

if __name__ == "__main__":
    import time
    # 独立运行测试：红、绿、蓝切换
    ScreenPatternTester.show("#FF0000")
    time.sleep(1)
    ScreenPatternTester.show("#00FF00")
    time.sleep(1)
    ScreenPatternTester.show("#0000FF")
    time.sleep(1)
    ScreenPatternTester.show("#000000")
    time.sleep(1)
    ScreenPatternTester.show("#FFFFFF")
    time.sleep(1)
    ScreenPatternTester.close()