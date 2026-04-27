import subprocess
import os


class CA40Tester:
    CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
    EXE_PATH = os.path.join(CURRENT_DIR, "cas40.exe")
    TXT_PATH = os.path.join(CURRENT_DIR, "data.txt")

    @classmethod
    def measure(cls):
        if not os.path.exists(cls.EXE_PATH):
            print(f"❌ 错误：找不到 {cls.EXE_PATH}")
            return None

        # 清理旧数据，防止读到假死数据
        if os.path.exists(cls.TXT_PATH):
            try:
                os.remove(cls.TXT_PATH)
            except Exception as e:
                print(f"⚠️ 警告：无法清理旧的 data.txt，可能被占用！({e})")

        try:
            print(f"🚀 正在调用 CA40: {cls.EXE_PATH} ...")

            # ================== 核心加固区 ==================
            # 1. 取消列表传参，直接传纯字符串路径
            # 2. shell=False：抛弃 cmd.exe 壳子，直接底层执行 exe，不受 GUI 环境干扰
            # 3. capture_output=True：把 C++ 程序内部的黑框框输出强行截获出来
            result = subprocess.run(
                cls.EXE_PATH,
                shell=False,
                cwd=cls.CURRENT_DIR,
                capture_output=True,
                text=True,
                encoding="gbk"  # 如果 C++ 输出乱码，可能需要改成 utf-8
            )

            # 检查 C++ 程序是否非正常退出
            if result.returncode != 0:
                print(f"❌ 仪器程序崩溃退出！错误码: {result.returncode}")
                print(f"📝 仪器内部报错: {result.stderr.strip()}")
                print(f"📝 仪器终端输出: {result.stdout.strip()}")
                return None

            # ================================================

            print("✅ 测量程序执行完毕！")

            if not os.path.exists(cls.TXT_PATH):
                print(f"❌ 致命错误：exe 成功跑完，但没有生成 {cls.TXT_PATH}！")
                print("👇 下面是 exe 运行时的控制台日志，看看它到底在干嘛：")
                print(result.stdout.strip() if result.stdout else "（没有任何输出）")
                return None

            with open(cls.TXT_PATH, "r", encoding="utf-8") as f:
                lv_value = f.read().strip()

            lv_float = float(lv_value)
            print(f"\n📊 成功读取亮度 Lv = {lv_float}")
            return lv_float

        except Exception as e:
            print(f"❌ Python 调起 exe 时发生严重异常：{str(e)}")
            return None


# ====================== 独立运行测试 ======================
if __name__ == "__main__":
    lv_result = CA40Tester.measure()
    if lv_result is not None:
        print(f"🎉 最终亮度值：{lv_result:.6f}")
    input("\n按回车退出")