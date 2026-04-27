import cv2
import os
import glob


def calculate_blur_laplacian_variance(image_path):
    """
    计算图像的拉普拉斯方差。
    返回值越大，代表图像边缘越丰富，通常意味着图像越清晰（越不模糊）。
    """
    image = cv2.imread(image_path)
    if image is None:
        return 0.0

    # 转换为灰度图以提升计算效率
    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)

    # 计算拉普拉斯算子后的方差
    variance = cv2.Laplacian(gray, cv2.CV_64F).var()
    return variance


def sort_images_by_sharpness(folder_path):
    """
    读取文件夹内的所有图片，按清晰度评分从高到低排序并打印结果。
    """
    # 支持常见的图片格式
    search_pattern = os.path.join(folder_path, "*.[jJ][pP][gG]")
    image_paths = glob.glob(search_pattern)

    if not image_paths:
        search_pattern_png = os.path.join(folder_path, "*.[pP][nN][gG]")
        image_paths = glob.glob(search_pattern_png)

    if not image_paths:
        print(f"未在 {folder_path} 中找到图片。")
        return []

    print(f"找到 {len(image_paths)} 张图片，正在进行清晰度评估...")

    image_scores = []
    for path in image_paths:
        score = calculate_blur_laplacian_variance(path)
        image_scores.append((path, score))

    # 按分数降序排列（分数最高的，即最清晰的排在前面）
    image_scores.sort(key=lambda x: x[1], reverse=True)

    print("\n--- 清晰度排名 ---")
    for rank, (path, score) in enumerate(image_scores, 1):
        filename = os.path.basename(path)
        print(f"Rank {rank}: {filename} - Score: {score:.2f}")

    return image_scores


if __name__ == "__main__":
    # 请将此处的路径替换为您第一步保存照片的文件夹路径
    capture_folder = "osd_captures/20260413_095036"

    sorted_images = sort_images_by_sharpness(capture_folder)

    # 此时可以根据排序结果，手动查看前几名是否符合您的预期