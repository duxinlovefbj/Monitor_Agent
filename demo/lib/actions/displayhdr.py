import subprocess
import time
import pyautogui

class DisplayHDRController:
    """
    DisplayHDR 测试工具自动化控制器
    """
    @staticmethod
    def launch(exe_path=r"C:\Path\To\DisplayHDRComplianceTests.exe"):
        """启动 DisplayHDR 软件"""
        try:
            subprocess.Popen(exe_path)
            time.sleep(3)  # 等待软件启动和获取焦点
            return True
        except Exception as e:
            print(f"启动 DisplayHDR 失败: {e}")
            return False

    @staticmethod
    def press_key(key_name, presses=1, interval=0.5):
        """
        向当前活动窗口发送键盘指令
        常用按键定义: 'pageup', 'pagedown', 'up', 'down', 'left', 'right', 'esc', 'space', 'enter'
        """
        pyautogui.press(key_name, presses=presses, interval=interval)

    @staticmethod
    def next_pattern():
        """示例组合动作：切换下一个测试画面"""
        pyautogui.press('pagedown')

    @staticmethod
    def prev_pattern():
        """示例组合动作：切换上一个测试画面"""
        pyautogui.press('pageup')