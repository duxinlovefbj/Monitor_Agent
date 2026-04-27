from typing import Optional
from serial.tools import list_ports

from demo.lib.ca410.ca410_ui import (
    CA410Probe,
    MeasurementResult,
    match_port_by_vid_pid,
    score_port_metadata,
    active_probe_port,
)


def find_ca410_port() -> str:
    """
    自动寻找 CA-410 串口。
    优先级：
    1. VID/PID 精确匹配
    2. 端口描述打分
    3. 主动发送 BPR 探测
    """

    exact_matches = match_port_by_vid_pid()
    if exact_matches:
        return exact_matches[0][0]

    ports = list(list_ports.comports())
    if ports:
        ranked = sorted(ports, key=score_port_metadata, reverse=True)
        best = ranked[0]
        best_score = score_port_metadata(best)

        if best_score >= 300:
            return best.device

    active_matches = active_probe_port(timeout=0.25)
    if active_matches:
        return active_matches[0][0]

    raise RuntimeError("未自动识别到 CA-410 串口")


def measure_ca410_once(
    port: Optional[str] = None,
    zero_cal_before_measure: bool = True,
    timeout: float = 5.0,
) -> MeasurementResult:
    """
    外部模块调用入口：
    自动连接一个串口，测量一次，返回一个 MeasurementResult。
    """

    if port is None:
        port = find_ca410_port()

    device = CA410Probe(port=port, timeout=timeout)

    try:
        device.open()
        result = device.measure_once(
            zero_cal_before_measure=zero_cal_before_measure
        )
        return result
    finally:
        device.close()