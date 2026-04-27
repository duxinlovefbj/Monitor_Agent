from demo.lib.ca410.ca410_control import CA410Controller


def measure_ca410(zero_cal_before_measure: bool = False, label: str = "") -> dict:
    data = CA410Controller.measure_and_get_data(zero_cal_before_measure=zero_cal_before_measure)
    if data is None:
        raise RuntimeError("CA410 未返回有效数据")

    if label:
        data["label"] = label
    return data
