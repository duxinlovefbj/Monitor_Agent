from demo.lib.ca410.ca410_module import measure_ca410_once
from dataclasses import asdict


class CA410Controller:
    """色彩分析仪数据读取模块"""

    @staticmethod
    def measure_and_get_data(zero_cal_before_measure=False):
        """
        触发 CA410 测量，并以字典形式返回所有数据
        """
        try:
            result = measure_ca410_once(
                zero_cal_before_measure=zero_cal_before_measure
            )
            data = asdict(result)
            return data
        except Exception as e:
            print(f"❌ CA410 测量失败: {e}")
            return None