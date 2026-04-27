import cv2
import numpy as np
from paddleocr import PaddleOCR

# 1. 初始化 (保持之前的稳定配置)
ocr = PaddleOCR(
    use_textline_orientation=True,
    lang="en",
    ocr_version="PP-OCRv4",
    enable_mkldnn=False,
    text_det_unclip_ratio=1.6
)


def analyze_menu_state(img_path):
    img = cv2.imread(img_path)
    if img is None:
        raise ValueError("图片读取失败。")

    results = ocr.predict(img_path)
    parsed_menu = []

    for res in results:
        # 3.x 版本的标准数据提取方式
        # 如果是老版本转新版本，这是最关键的改动点
        try:
            items = zip(res['dt_polys'], res['rec_texts'], res['rec_scores'])
        except KeyError:
            # 万一键名变动（如某些预览版），打印所有键名进行排查
            print(f"当前结果中的可用键: {res.doc_res.keys()}")
            continue

        for bbox, text, confidence in items:
            pts = np.array(bbox, np.int32)
            x, y, w, h = cv2.boundingRect(pts)

            state = "未知"

            # --- A. 选中判定 (技嘉 UI 专用) ---
            left_x = max(0, int(x - h * 1.5))
            check_roi = img[y:y + h, left_x:x]

            is_selected = False
            if check_roi.size > 0:
                hsv_roi = cv2.cvtColor(check_roi, cv2.COLOR_BGR2HSV)
                # 调整后的 HSV 阈值：降低饱和度要求以适应摩尔纹
                lower_cyan = np.array([75, 40, 40])
                upper_cyan = np.array([115, 255, 255])
                mask = cv2.inRange(hsv_roi, lower_cyan, upper_cyan)

                cyan_ratio = cv2.countNonZero(mask) / (check_roi.shape[0] * check_roi.shape[1] + 1e-5)
                if cyan_ratio > 0.05:
                    is_selected = True
                    state = "选中 (Selected)"

            # --- B. 置灰判定 ---
            if not is_selected:
                text_roi = img[y:y + h, x:x + w]
                if text_roi.size > 0:
                    gray_roi = cv2.cvtColor(text_roi, cv2.COLOR_BGR2GRAY)
                    flat_gray = gray_roi.flatten()
                    top_10 = max(1, int(len(flat_gray) * 0.1))
                    flat_gray.sort()
                    text_brightness = np.mean(flat_gray[-top_10:])

                    if text_brightness < 110:
                        state = f"不可选 (Disabled) [L:{text_brightness:.0f}]"
                    else:
                        state = f"未选中 (Unselected) [L:{text_brightness:.0f}]"

            parsed_menu.append({"text": text, "state": state, "confidence": confidence})
            print(f"文本: {text: <18} | 置信度: {confidence:.2f} | 状态: {state}")

    return parsed_menu


# 测试运行
analyze_menu_state(r"C:\Users\Administrator\PycharmProjects\Monitor_Agent\demo\photo_demo\final_osd_result.jpg")