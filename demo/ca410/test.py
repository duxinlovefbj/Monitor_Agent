import csv
import math
import queue
import threading
from dataclasses import dataclass, asdict
from datetime import datetime
from typing import Optional, List, Tuple

import serial
from serial.tools import list_ports
import tkinter as tk
from tkinter import ttk, filedialog, messagebox
import traceback


APP_TITLE = "CA-410 Probe Compare Tool"
DEFAULT_BAUDRATE = 38400
WHITEPOINT_E = (1.0 / 3.0, 1.0 / 3.0)


@dataclass
class MeasurementResult:
    port: str
    probe: str
    status: int

    x: float
    y: float
    lv: float

    X: float
    Y: float
    Z: float

    u_prime: float
    v_prime: float

    cct: Optional[float]
    duv: Optional[float]
    dominant_or_complementary_wavelength_nm: Optional[float]
    excitation_purity_percent: Optional[float]

    measured_at: str

    raw_mds0: str
    raw_mds1: str
    raw_mds5: str
    raw_mds7: str
    raw_mds8: str

    notes: str = ""

    def to_csv_row(self):
        return asdict(self)


def safe_float(value: str) -> float:
    return float(value.strip())


def xy_to_upvp(x: float, y: float) -> Tuple[float, float]:
    denom = (-2.0 * x) + (12.0 * y) + 3.0
    if abs(denom) < 1e-12:
        return float("nan"), float("nan")
    u_prime = (4.0 * x) / denom
    v_prime = (9.0 * y) / denom
    return u_prime, v_prime


def xy_to_uv1960(x: float, y: float) -> Tuple[float, float]:
    denom = (-2.0 * x) + (12.0 * y) + 3.0
    if abs(denom) < 1e-12:
        return float("nan"), float("nan")
    u = (4.0 * x) / denom
    v = (6.0 * y) / denom
    return u, v


def xy_to_cct_mccamy(x: float, y: float) -> Optional[float]:
    # 仅作为 colour-science 不可用时的近似回退
    xe, ye = 0.3320, 0.1858
    if abs(y - ye) < 1e-12:
        return None
    n = (x - xe) / (y - ye)
    return -449.0 * (n ** 3) + 3525.0 * (n ** 2) - 6823.3 * n + 5520.33


def compute_derived_with_colour(x: float, y: float):
    try:
        import numpy as np
        import colour
        from colour.colorimetry import MSDS_CMFS
        from colour.temperature import uv_to_CCT_Ohno2013

        # 将 xy 转换为 uv 1960 坐标
        uv = np.array(xy_to_uv1960(x, y))

        # 获取标准观察者的色匹配函数（必需参数）
        cmfs = MSDS_CMFS["CIE 1931 2 Degree Standard Observer"]

        # uv_to_CCT_Ohno2013 需要传入 cmfs 参数
        cct_duv = uv_to_CCT_Ohno2013(uv, cmfs)

        # 不同版本返回格式可能有差异，尽量兼容
        if hasattr(cct_duv, "__len__") and len(cct_duv) >= 2:
            cct = float(cct_duv[0])
            duv = float(cct_duv[1])
        else:
            cct = float(cct_duv)
            duv = None

        # 计算主波长和激发纯度
        xy = np.array([x, y], dtype=float)
        xy_n = np.array(WHITEPOINT_E, dtype=float)  # 等能白点

        wl_result = colour.dominant_wavelength(xy, xy_n, cmfs)
        if hasattr(wl_result, "__len__") and len(wl_result) >= 1:
            wavelength = float(wl_result[0])
        else:
            wavelength = float(wl_result)

        purity = float(colour.excitation_purity(xy, xy_n, cmfs)) * 100.0
        return cct, duv, wavelength, purity, "colour-science"
    except Exception as exc:
        return None, None, None, None, f"colour-science unavailable: {exc}"


def compute_derived(x: float, y: float):
    cct, duv, wavelength, purity, note = compute_derived_with_colour(x, y)
    if cct is None:
        cct = xy_to_cct_mccamy(x, y)
        note = f"{note}; fallback CCT=McCamy approximation"
    return cct, duv, wavelength, purity, note


class CA410Probe:
    def __init__(self, port: str, timeout: float = 5.0):
        self.port = port
        self.timeout = timeout
        self.ser: Optional[serial.Serial] = None

    def open(self):
        if self.ser and self.ser.is_open:
            return
        self.ser = serial.Serial(
            port=self.port,
            baudrate=DEFAULT_BAUDRATE,
            bytesize=serial.SEVENBITS,
            parity=serial.PARITY_EVEN,
            stopbits=serial.STOPBITS_TWO,
            rtscts=True,
            timeout=self.timeout,
        )

    def close(self):
        if self.ser and self.ser.is_open:
            self.ser.close()

    def send_cmd(self, cmd: str) -> str:
        if not self.ser or not self.ser.is_open:
            raise RuntimeError("串口未打开。")
        self.ser.reset_input_buffer()
        self.ser.write((cmd + "\r").encode("ascii"))
        self.ser.flush()
        resp = self.ser.read_until(b"\r")
        if not resp:
            raise TimeoutError(f"命令超时: {cmd}")
        return resp.decode("ascii", errors="replace").strip("\r")

    def expect_ok(self, cmd: str) -> str:
        resp = self.send_cmd(cmd)
        if not resp.startswith("OK"):
            raise RuntimeError(f"命令失败: {cmd} -> {resp}")
        return resp

    def probe_identity(self) -> Optional[str]:
        try:
            return self.expect_ok("BPR")
        except Exception:
            return None

    def measure_once(self, zero_cal_before_measure: bool = True) -> MeasurementResult:
        self.expect_ok("LUS,1")
        if zero_cal_before_measure:
            self.expect_ok("ZRC")

        # 1) x, y, Lv
        self.expect_ok("MDS,0")
        raw_mds0 = self.expect_ok("MES,1")
        parts0 = raw_mds0.split(",")

        # 2) Tcp, duv, Lv
        self.expect_ok("MDS,1")
        raw_mds1 = self.expect_ok("MES,1")
        parts1 = raw_mds1.split(",")

        # 3) u', v', Lv
        self.expect_ok("MDS,5")
        raw_mds5 = self.expect_ok("MES,1")
        parts5 = raw_mds5.split(",")

        # 4) X, Y, Z
        self.expect_ok("MDS,7")
        raw_mds7 = self.expect_ok("MES,1")
        parts7 = raw_mds7.split(",")

        # 5) λd, Pe, Lv
        self.expect_ok("MDS,8")
        raw_mds8 = self.expect_ok("MES,1")
        parts8 = raw_mds8.split(",")

        x = safe_float(parts0[3])
        y = safe_float(parts0[4])
        lv = safe_float(parts0[5])

        cct = safe_float(parts1[3])
        duv = safe_float(parts1[4])

        u_prime = safe_float(parts5[3])
        v_prime = safe_float(parts5[4])

        X = safe_float(parts7[3])
        Y = safe_float(parts7[4])
        Z = safe_float(parts7[5])

        wavelength = safe_float(parts8[3])
        purity = safe_float(parts8[4])

        probe = parts0[1]
        status = int(parts0[2])

        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        return MeasurementResult(
            port=self.port,
            probe=probe,
            status=status,

            x=x,
            y=y,
            lv=lv,

            X=X,
            Y=Y,
            Z=Z,

            u_prime=u_prime,
            v_prime=v_prime,

            cct=cct,
            duv=duv,
            dominant_or_complementary_wavelength_nm=wavelength,
            excitation_purity_percent=purity,

            measured_at=timestamp,

            raw_mds0=raw_mds0,
            raw_mds1=raw_mds1,
            raw_mds5=raw_mds5,
            raw_mds7=raw_mds7,
            raw_mds8=raw_mds8,

            notes="Device direct read via MDS 0/1/5/7/8",
        )

def match_port_by_vid_pid() -> list:
    matches = []
    for p in list_ports.comports():
        vid = getattr(p, "vid", None)
        pid = getattr(p, "pid", None)
        desc = str(getattr(p, "description", "") or "")
        hwid = str(getattr(p, "hwid", "") or "")

        if vid == 0x132B and pid == 0x210D:
            matches.append((p.device, desc, hwid))
    return matches

def score_port_metadata(port_info) -> int:
    text = " | ".join(
        str(getattr(port_info, attr, "") or "")
        for attr in ("device", "description", "manufacturer", "product", "hwid")
    ).upper()

    vid = getattr(port_info, "vid", None)
    pid = getattr(port_info, "pid", None)

    score = 0

    # 你的设备特征，最高优先级
    if vid == 0x132B and pid == 0x210D:
        score += 1000

    for keyword, pts in [
        ("MEASURING INSTRUMENTS", 300),
        ("KONICA", 120),
        ("MINOLTA", 120),
        ("CA-410", 200),
        ("CA410", 200),
        ("USB", 5),
        ("SERIAL", 5),
    ]:
        if keyword in text:
            score += pts

    return score


def active_probe_port(timeout: float = 0.25) -> list:
    matches = []
    for p in list_ports.comports():
        try:
            ser = serial.Serial(
                port=p.device,
                baudrate=DEFAULT_BAUDRATE,
                bytesize=serial.SEVENBITS,
                parity=serial.PARITY_EVEN,
                stopbits=serial.STOPBITS_TWO,
                rtscts=True,
                timeout=timeout,
                write_timeout=timeout,
            )
            ser.reset_input_buffer()
            ser.write(b"BPR\r")
            ser.flush()
            resp = ser.read_until(b"\r").decode("ascii", errors="replace").strip("\r")
            ser.close()

            if resp.startswith("OK00,38400"):
                matches.append((p.device, resp))
        except Exception:
            continue
    return matches


class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title(APP_TITLE)
        self.geometry("980x720")
        self.minsize(900, 650)

        self.device: Optional[CA410Probe] = None
        self.last_result: Optional[MeasurementResult] = None
        self.worker_queue: queue.Queue = queue.Queue()

        self.port_var = tk.StringVar()
        self.status_var = tk.StringVar(value="未连接")
        self.zero_cal_var = tk.BooleanVar(value=True)

        self._build_ui()
        self.refresh_ports()
        self.after(100, self._poll_queue)

    def _build_ui(self):
        top = ttk.Frame(self, padding=12)
        top.pack(fill="x")

        ttk.Label(top, text="串口").grid(row=0, column=0, sticky="w")
        self.port_combo = ttk.Combobox(top, textvariable=self.port_var, width=24, state="readonly")
        self.port_combo.grid(row=0, column=1, padx=6, sticky="w")

        ttk.Button(top, text="刷新串口", command=self.refresh_ports).grid(row=0, column=2, padx=4)
        ttk.Button(top, text="自动匹配", command=self.auto_match).grid(row=0, column=3, padx=4)
        ttk.Button(top, text="连接", command=self.connect).grid(row=0, column=4, padx=4)
        ttk.Button(top, text="断开", command=self.disconnect).grid(row=0, column=5, padx=4)

        ttk.Checkbutton(top, text="测量前零校准", variable=self.zero_cal_var).grid(row=1, column=1, sticky="w", pady=(8, 0))
        ttk.Button(top, text="测量一次", command=self.measure_once).grid(row=1, column=2, padx=4, pady=(8, 0))
        ttk.Button(top, text="导出本次 CSV", command=self.export_last_result).grid(row=1, column=3, padx=4, pady=(8, 0))

        ttk.Label(top, textvariable=self.status_var).grid(row=1, column=4, columnspan=2, sticky="w", padx=(8, 0), pady=(8, 0))

        self.result_frame = ttk.LabelFrame(self, text="测量结果", padding=12)
        self.result_frame.pack(fill="x", padx=12, pady=(0, 8))

        self.value_vars = {}
        fields = [
            ("X", "X"), ("Y", "Y"), ("Z", "Z"),
            ("x", "x"), ("y", "y"), ("Lv [cd/m²]", "lv"),
            ("u'", "u_prime"), ("v'", "v_prime"),
            ("Tcp / CCT [K]", "cct"), ("duv", "duv"),
            ("λd/λc [nm]", "dominant_or_complementary_wavelength_nm"),
            ("Pe [%]", "excitation_purity_percent"),
            ("Probe", "probe"), ("Status", "status"), ("Time", "measured_at"),
        ]
        for i, (label, key) in enumerate(fields):
            row = i // 3
            col = (i % 3) * 2
            ttk.Label(self.result_frame, text=label).grid(row=row, column=col, sticky="w", padx=(0, 8), pady=4)
            var = tk.StringVar(value="-")
            self.value_vars[key] = var
            ttk.Entry(self.result_frame, textvariable=var, width=28, state="readonly").grid(row=row, column=col + 1, sticky="ew", pady=4)

        self.result_frame.columnconfigure(1, weight=1)
        self.result_frame.columnconfigure(3, weight=1)
        self.result_frame.columnconfigure(5, weight=1)

        raw_frame = ttk.LabelFrame(self, text="原始响应 / 日志", padding=12)
        raw_frame.pack(fill="both", expand=True, padx=12, pady=(0, 12))
        self.log_text = tk.Text(raw_frame, wrap="word", height=18)
        self.log_text.pack(fill="both", expand=True)

    def log(self, message: str):
        self.log_text.insert("end", f"{datetime.now().strftime('%H:%M:%S')}  {message}\n")
        self.log_text.see("end")

    def refresh_ports(self):
        ports = sorted([p.device for p in list_ports.comports()])
        self.port_combo["values"] = ports
        if ports and (self.port_var.get() not in ports):
            self.port_var.set(ports[0])
        self.log(f"发现串口: {ports if ports else '无'}")

    def auto_match(self):
        self.log("开始自动匹配 CA-410 探头...")

        # 1. 先按 VID/PID 精确匹配
        exact_matches = match_port_by_vid_pid()
        if exact_matches:
            chosen = exact_matches[0][0]
            self.port_var.set(chosen)
            self.status_var.set(f"按 VID/PID 匹配: {chosen}")
            self.log(f"VID/PID 精确命中: {exact_matches}")
            return

        # 2. 再按描述和硬件信息打分
        ports = list(list_ports.comports())
        if ports:
            ranked = sorted(ports, key=score_port_metadata, reverse=True)
            best = ranked[0]
            best_score = score_port_metadata(best)
            if best_score >= 300:
                self.port_var.set(best.device)
                self.status_var.set(f"按端口信息匹配: {best.device}")
                self.log(
                    f"端口信息高置信匹配: {best.device} | "
                    f"description={getattr(best, 'description', '')} | "
                    f"hwid={getattr(best, 'hwid', '')}"
                )
                return

        # 3. 最后才主动探测，且超时很短
        self.log("未命中静态特征，开始短超时主动探测...")
        active_matches = active_probe_port(timeout=0.25)
        if active_matches:
            chosen = active_matches[0][0]
            self.port_var.set(chosen)
            self.status_var.set(f"主动探测匹配: {chosen}")
            self.log(f"主动探测成功: {active_matches}")
            return

        messagebox.showinfo(
            APP_TITLE,
            "没有自动识别到 CA-410。\n\n请先点击“刷新串口”，再手动选择端口。"
        )

    def connect(self):
        port = self.port_var.get().strip()
        if not port:
            messagebox.showwarning(APP_TITLE, "请先选择串口。")
            return
        try:
            if self.device:
                self.device.close()
            self.device = CA410Probe(port)
            self.device.open()
            identity = self.device.probe_identity()
            self.status_var.set(f"已连接: {port}")
            self.log(f"连接成功: {port}")
            if identity:
                self.log(f"BPR -> {identity}")
        except Exception as exc:
            self.device = None
            self.status_var.set("连接失败")
            messagebox.showerror(APP_TITLE, f"连接失败：{exc}")

    def disconnect(self):
        try:
            if self.device:
                self.device.close()
            self.device = None
            self.status_var.set("未连接")
            self.log("已断开连接。")
        except Exception as exc:
            messagebox.showerror(APP_TITLE, f"断开失败：{exc}")

    def measure_once(self):
        if not self.device:
            self.connect()
            if not self.device:
                return

        self.status_var.set("测量中...")
        self.log("开始测量...")
        threading.Thread(target=self._measure_worker, daemon=True).start()

    def _measure_worker(self):
        try:
            result = self.device.measure_once(
                zero_cal_before_measure=self.zero_cal_var.get()
            )
            self.worker_queue.put(("result", result))
        except Exception:
            self.worker_queue.put(("error", traceback.format_exc()))

    def _poll_queue(self):
        try:
            while True:
                kind, payload = self.worker_queue.get_nowait()
                if kind == "result":
                    self.last_result = payload
                    self._update_result_view(payload)
                    self.status_var.set("测量完成")
                    self.log("测量完成。")
                    self.log(f"MDS,0 -> {payload.raw_mds0}")
                    self.log(f"MDS,1 -> {payload.raw_mds1}")
                    self.log(f"备注 -> {payload.notes}")
                elif kind == "error":
                    self.status_var.set("测量失败")
                    self.log("测量失败，完整 traceback 如下：")
                    self.log(payload)
                    messagebox.showerror(APP_TITLE, f"测量失败：\n{payload}")
        except queue.Empty:
            pass
        self.after(100, self._poll_queue)

    def _fmt(self, value):
        if value is None:
            return "-"
        if isinstance(value, float):
            if math.isnan(value):
                return "-"
            return f"{value:.6f}"
        return str(value)

    def _update_result_view(self, result: MeasurementResult):
        for key, var in self.value_vars.items():
            var.set(self._fmt(getattr(result, key)))

    def export_last_result(self):
        if not self.last_result:
            messagebox.showwarning(APP_TITLE, "还没有可导出的测量结果。")
            return

        path = filedialog.asksaveasfilename(
            title="保存 CSV",
            defaultextension=".csv",
            filetypes=[("CSV 文件", "*.csv"), ("所有文件", "*.*")],
            initialfile=f"ca410_measurement_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv",
        )
        if not path:
            return

        row = self.last_result.to_csv_row()
        with open(path, "w", newline="", encoding="utf-8-sig") as f:
            writer = csv.DictWriter(f, fieldnames=list(row.keys()))
            writer.writeheader()
            writer.writerow(row)

        self.log(f"CSV 已导出: {path}")
        messagebox.showinfo(APP_TITLE, f"CSV 已导出：\n{path}")


if __name__ == "__main__":
    app = App()
    app.mainloop()
