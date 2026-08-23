"""最简方案：bbox中心作为圆心 + 自适应阈值"""
import cv2
import numpy as np
from pathlib import Path
from scipy import ndimage

src = Path(r'd:\projects\cyber_stamping\backend\test_output\module_test\8181.jpg')
img = cv2.imread(str(src))
h, w = img.shape[:2]

# 用户 bbox 框选印章区域
cx, cy = w//2, int(h*0.55)
r_roi = int(min(w,h)*0.25)
x0, y0, x1, y1 = max(0,cx-r_roi), max(0,cy-r_roi), min(w,cx+r_roi), min(h,cy+r_roi)
roi_bgr = img[y0:y1, x0:x1]
roi_h, roi_w = roi_bgr.shape[:2]
print(f"ROI: {roi_w}x{roi_h}")
print(f"ROI center: ({roi_w//2}, {roi_h//2})")

def capture_rate(alpha, threshold=32):
    center_x, center_y = roi_w // 2, roi_h // 2
    rates = {}
    for angle_deg in [0, 45, 90, 135, 180, 225, 270, 315]:
        angle = np.radians(angle_deg)
        captured = 0
        total = 0
        for dist in range(int(roi_w * 0.1), int(roi_w * 0.48), 3):
            px_x = int(center_x + dist * np.cos(angle))
            px_y = int(center_y + dist * np.sin(angle))
            if 0 <= px_x < roi_w and 0 <= px_y < roi_h:
                total += 1
                if alpha[px_y, px_x] > threshold:
                    captured += 1
        rates[angle_deg] = captured / total * 100 if total > 0 else 0
    return rates

def save_diag(name, mask):
    rates = capture_rate(mask, 32)
    avg = np.mean(list(rates.values()))
    print(f"  [{name}] fg={cv2.countNonZero(mask)/(roi_w*roi_h)*100:.1f}% avg={avg:.0f}%")
    print(f"     rates: {[f'{k}={v:.0f}%' for k,v in rates.items()]}")
    cv2.imwrite(str(Path(f'test_output/diag_{name}.png')), mask)
    full_mask = np.zeros((h, w), dtype=np.uint8)
    full_mask[y0:y0+roi_h, x0:x0+roi_w] = mask
    rgba = np.dstack([img, full_mask])
    cv2.imwrite(str(Path(f'test_output/diag_{name}_rgba.png')), rgba)

# ---- 核心算法 ----
gray = cv2.cvtColor(roi_bgr, cv2.COLOR_BGR2GRAY)

# 1. 多种对比度/通道组合
configs = []

# 灰度
clahe = cv2.createCLAHE(clipLimit=3.0, tileGridSize=(8, 8))
enhanced_gray = clahe.apply(gray)
configs.append(("gray_CLAHE3", enhanced_gray, cv2.THRESH_BINARY_INV))

# R-G 增强通道
b_ch, g_ch, r_ch = cv2.split(roi_bgr)
r_enh = (r_ch.astype(np.int16) - g_ch.astype(np.int16)).clip(-128, 127).astype(np.int8)
r_u8 = (r_enh.astype(np.int16) + 128).clip(0, 255).astype(np.uint8)
enhanced_r = clahe.apply(r_u8)
configs.append(("r-g_CLAHE3", enhanced_r, cv2.THRESH_BINARY))  # R-G 高值=前景

# 2. 圆半径倍数
radius_mults = [0.45, 0.47, 0.48]

best = None
best_avg = 0

# 3. 遍历组合
for ch_name, ch_img, thresh_type in configs:
    for bs in [21, 31, 51, 71]:
        if bs % 2 == 0: bs += 1
        for c in [2, 3, 5]:
            try:
                binary = cv2.adaptiveThreshold(ch_img, 255, cv2.ADAPTIVE_THRESH_MEAN_C, thresh_type, bs, c)
            except Exception as e:
                continue
            for rm in radius_mults:
                # 创建圆形蒙版
                center_x, center_y = roi_w // 2, roi_h // 2
                circle_r = int(min(roi_w, roi_h) * rm)
                circle_m = np.zeros((roi_h, roi_w), dtype=np.uint8)
                cv2.circle(circle_m, (center_x, center_y), circle_r, 255, -1)
                
                # 交集
                masked = cv2.bitwise_and(binary, circle_m)
                
                # 去噪
                k2 = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (2, 2))
                cleaned = cv2.morphologyEx(masked, cv2.MORPH_OPEN, k2)
                
                # 连通块去噪
                labeled, num = ndimage.label(cleaned > 0)
                if num == 0: continue
                sizes = ndimage.sum(cleaned > 0, labeled, range(1, num + 1))
                min_sz = 20
                keep = np.zeros_like(cleaned > 0, dtype=bool)
                for i in range(1, num + 1):
                    if sizes[i-1] >= min_sz:
                        keep = keep | (labeled == i)
                final = keep.astype(np.uint8) * 255
                
                rates = capture_rate(final, 32)
                avg = np.mean(list(rates.values()))
                fg = cv2.countNonZero(final) / (roi_w*roi_h) * 100
                
                if avg > best_avg and 10 < fg < 60:
                    best_avg = avg
                    best = (ch_name, bs, c, rm, final, rates, fg, avg)

# 输出所有参数组合中最好的 10 个
# （上面只记录了1个，简化直接输出最好的）
if best:
    ch_name, bs, c, rm, final, rates, fg, avg = best
    print(f"\n=== BEST: {ch_name} bs={bs} c={c} r_mult={rm} ===")
    print(f"  fg={fg:.1f}% avg={avg:.0f}%")
    print(f"  rates: {[f'{k}={v:.0f}%' for k,v in rates.items()]}")
    save_diag("FINAL_CIRCLE_BEST", final)
else:
    print("No valid result found!")
