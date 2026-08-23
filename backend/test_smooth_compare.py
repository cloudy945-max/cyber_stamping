"""生成边缘平滑前后对比图"""
import cv2
import numpy as np

OUT_DIR = r'd:\projects\cyber_stamping\backend\test_output\api_test'
bg_color = (245, 230, 200)  # #f5e6c8

versions = [
    ('v_before_smooth', '平滑前 (当前版)'),
    ('v_smooth', '平滑后 (优化版)'),
]

imgs = []
for name, label in versions:
    path = f'{OUT_DIR}\\{name}.png'
    img = cv2.imread(path, cv2.IMREAD_UNCHANGED)
    alpha = img[:, :, 3]
    ys, xs = np.where(alpha >= 10)
    if len(ys) == 0:
        imgs.append(np.zeros((100, 100, 3), dtype=np.uint8))
        continue
    x0, x1 = xs.min(), xs.max()
    y0, y1 = ys.min(), ys.max()
    pad = 30
    x0 = max(0, x0 - pad); y0 = max(0, y0 - pad)
    x1 = min(img.shape[1], x1 + pad); y1 = min(img.shape[0], y1 + pad)
    crop = img[y0:y1, x0:x1]
    bg = np.full((crop.shape[0], crop.shape[1], 3), bg_color, dtype=np.uint8)
    a = crop[:, :, 3:4].astype(np.float32) / 255.0
    composite = (crop[:, :, :3].astype(np.float32) * a + bg.astype(np.float32) * (1 - a)).astype(np.uint8)
    imgs.append(composite)

# 统一高度
target_h = 700
resized = []
for im in imgs:
    h, w = im.shape[:2]
    scale = target_h / h
    new_w = int(w * scale)
    resized.append(cv2.resize(im, (new_w, target_h)))

# 横向拼接
gap = 20
total_w = sum(im.shape[1] for im in resized) + gap * (len(resized) - 1)
canvas = np.full((target_h + 40, total_w, 3), bg_color, dtype=np.uint8)
x_offset = 0
labels = [v[1] for v in versions]
for i, im in enumerate(resized):
    canvas[:target_h, x_offset:x_offset + im.shape[1]] = im
    cv2.putText(canvas, labels[i], (x_offset + 5, target_h + 25),
                cv2.FONT_HERSHEY_SIMPLEX, 0.6, (100, 80, 60), 1, cv2.LINE_AA)
    x_offset += im.shape[1] + gap

comp_path = f'{OUT_DIR}\\smooth_comparison.png'
cv2.imwrite(comp_path, canvas)
print(f"对比图已保存: {comp_path}")
