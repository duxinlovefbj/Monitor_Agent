import cv2
import numpy as np
import os


def align_and_stack_images(image_paths, output_path="final_stacked_osd.jpg"):
    """
    对多张图片进行特征对齐并进行均值堆栈合成，最后应用锐化。
    """
    if len(image_paths) < 2:
        print("错误：至少需要 2 张图片进行合成。")
        return

    print(f"准备合成 {len(image_paths)} 张图片...")

    # 1. 读取第一张图片作为“基准帧” (建议是清晰度最高的那张)
    print(f"读取基准帧: {image_paths[0]}")
    img_ref = cv2.imread(image_paths[0])
    if img_ref is None:
        print(f"无法读取基准帧: {image_paths[0]}")
        return

    h, w = img_ref.shape[:2]
    gray_ref = cv2.cvtColor(img_ref, cv2.COLOR_BGR2GRAY)

    # 创建浮点型数组用于累计像素值，防止数据溢出
    stacked_image_float = np.float32(img_ref)

    # 初始化 SIFT 探测器 (对于文字特征提取效果极佳)
    sift = cv2.SIFT_create()
    kp_ref, des_ref = sift.detectAndCompute(gray_ref, None)

    # 初始化特征匹配器 (暴力匹配 + KD树优化)
    matcher = cv2.BFMatcher()

    # 2. 循环处理剩余的图片并对齐
    for i in range(1, len(image_paths)):
        curr_path = image_paths[i]
        print(f"正在对齐并叠加第 {i + 1} 张: {curr_path} ...")

        img_curr = cv2.imread(curr_path)
        if img_curr is None:
            print(f"警告：无法读取 {curr_path}，已跳过。")
            continue

        gray_curr = cv2.cvtColor(img_curr, cv2.COLOR_BGR2GRAY)

        # 寻找当前帧的特征点
        kp_curr, des_curr = sift.detectAndCompute(gray_curr, None)

        # KNN 匹配
        matches = matcher.knnMatch(des_curr, des_ref, k=2)

        # 应用 Lowe's Ratio Test 筛选优质匹配点
        good_matches = []
        for m, n in matches:
            if m.distance < 0.75 * n.distance:
                good_matches.append(m)

        if len(good_matches) < 10:
            print(f"警告：{curr_path} 匹配点过少 ({len(good_matches)})，对齐可能失败，已跳过。")
            continue

        # 提取匹配点的坐标
        src_pts = np.float32([kp_curr[m.queryIdx].pt for m in good_matches]).reshape(-1, 1, 2)
        dst_pts = np.float32([kp_ref[m.trainIdx].pt for m in good_matches]).reshape(-1, 1, 2)

        # 计算单应性矩阵 (利用 RANSAC 算法剔除异常值)
        H, mask = cv2.findHomography(src_pts, dst_pts, cv2.RANSAC, 5.0)

        if H is not None:
            # 应用透视变换对齐图像
            aligned_img = cv2.warpPerspective(img_curr, H, (w, h))
            # 累加到浮点数组中
            stacked_image_float += np.float32(aligned_img)
        else:
            print(f"警告：无法计算 {curr_path} 的变换矩阵，已跳过。")

    # 3. 计算均值并转换回 uint8 格式
    print("对齐叠加完成，正在计算均值...")
    stacked_image_float /= len(image_paths)
    final_stacked = np.clip(stacked_image_float, 0, 255).astype(np.uint8)

    # 4. 后期处理：USM 锐化 (Unsharp Masking) 增强文字边缘
    print("正在进行 USM 锐化处理...")
    # 对图像进行高斯模糊
    blurred = cv2.GaussianBlur(final_stacked, (0, 0), 3)
    # 原图减去模糊图获得高频边缘，再叠加回原图
    # 公式：sharpened = original + (original - blurred) * amount
    sharpened = cv2.addWeighted(final_stacked, 1.5, blurred, -0.5, 0)

    # 5. 保存与预览
    cv2.imwrite(output_path, sharpened)
    print(f"\n合成大功告成！文件已保存至: {output_path}")

    # 缩放预览图 (4K直接显示会超出屏幕，缩放到 1920x1080 预览)
    preview = cv2.resize(sharpened, (1920, 1080))
    cv2.imshow("Stacked & Sharpened Preview (Scaled to 1080p)", preview)
    cv2.waitKey(0)
    cv2.destroyAllWindows()


if __name__ == "__main__":
    # ！！！请将这里的列表替换为您在上一步中筛选出的最清晰的5张照片的绝对或相对路径！！！
    # 建议将最清晰的那张（Rank 1）放在列表的第一个位置，作为对齐基准。
    top_5_images = [
        "osd_captures/20260413_095036/012.jpg",  # Rank 1 (作为对齐基准)
        "osd_captures/20260413_095036/011.jpg",  # Rank 2
        "osd_captures/20260413_095036/010.jpg",  # Rank 3
        "osd_captures/20260413_095036/013.jpg",  # Rank 4
        "osd_captures/20260413_095036/018.jpg"  # Rank 5
    ]

    # 确保文件都存在
    valid_paths = [p for p in top_5_images if os.path.exists(p)]

    if len(valid_paths) == len(top_5_images):
        align_and_stack_images(valid_paths, "final_osd_result.jpg")
    else:
        print("找不到部分图片文件，请检查上面的 top_5_images 路径填写是否正确。")