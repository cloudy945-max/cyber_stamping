"""基于连通块形状属性筛选真实笔画（细长结构）。
笔画特征：细长、宽度均匀、骨架化后长度远大于厚度。
背景斑点：大而圆、或面积小但宽高比接近 1。
"""
import os, sys, types
from pathlib import Path
import cv2
import numpy as np
from scipy import ndimage
from PIL import Image

if "pymatting.alpha.estimate_alpha_cf" not in sys.modules:
    stubs = {
        "pymatting": types.ModuleType("pymatting"),
        "pymatting.alpha": types.ModuleType("pymatting.alpha"),
        "pymatting.alpha.estimate_alpha_cf": types.ModuleType("pymatting.alpha.estimate_alpha_cf"),
        "pymatting.foreground": types.ModuleType("pymatting.foreground"),
        "pymatting.foreground.estimate_foreground_ml": types.ModuleType("pymatting.foreground.estimate_foreground_ml"),
        "pymatting.util": types.ModuleType("pymatting.util"),
        "pymatting.util.util": types.ModuleType("pymatting.util.util"),
    }
    for name, mod in stubs.items():
        if "." in name: mod.__path__ = []
    stubs["pymatting.alpha.estimate_alpha_cf"].estimate_alpha_cf = lambda *a, **kw: None
    stubs["pymatting.foreground.estimate_foreground_ml"].estimate_foreground_ml = lambda *a, **kw: None
    stubs["pymatting.util.util"].stack_images = lambda *a, **kw: None
    stubs["pymatting"].alpha = stubs["pymatting.alpha"]
    stubs["pymatting"].foreground = stubs["pymatting.foreground"]
    stubs["pymatting"].util = stubs["pymatting.util"]
    stubs["pymatting.alpha"].estimate_alpha_cf = stubs["pymatting.alpha.estimate_alpha_cf"]
    stubs["pymatting.foreground"].estimate_foreground_ml = stubs["pymatting.foreground.estimate_foreground_ml"]
    stubs["pymatting.util"].util = stubs["pymatting.util.util"]
    for name, mod in stubs.items():
        sys.modules.setdefault(name, mod)

from rembg import new_session, remove

src = Path(r'd:\projects\cyber_stamping\backend\test_output\module_test\8181.jpg')
img = cv2.imread(str(src))
h, w = img.shape[:2]
cx_img, cy_img = w//2, int(h*0.55)
r_roi = int(min(w,h)*0.25)
x0, y0, x1, y1 = max(0,cx_img-r_roi), max(0,cy_img-r_roi), min(w,cx_img+r_roi), min(h,cy_img+r_roi)
roi_bgr = img[y0:y1, x0:x1]
roi_h, roi_w = roi_bgr.shape[:2]
roi_path = Path('test_output/rembg_roi.jpg')
cv2.imwrite(str(roi_path), roi_bgr)

center_x, center_y = roi_w // 2, roi_h // 2
circle_r = int(min(roi_w, roi_h) * 0.48)
circle_m = np.zeros((roi_h, roi_w), dtype=np.uint8)
cv2.circle(circle_m, (center_x, center_y), circle_r, 255, -1)

k3 = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (3, 3))
session = new_session('u2netp')
with Image.open(roi_path) as pil_img:
    result = remove(pil_img, session=session)
    rembg_alpha = np.array(result)[:,:,3]
_, rembg_bin = cv2.threshold(rembg_alpha, 64, 255, cv2.THRESH_BINARY)

b_ch, g_ch, r_ch = cv2.split(roi_bgr)
r_enh = (r_ch.astype(np.int16) - g_ch.astype(np.int16)).clip(-128, 127).astype(np.int8)
r_u8 = (r_enh.astype(np.int16) + 128).clip(0, 255).astype(np.uint8)
clahe = cv2.createCLAHE(clipLimit=3.0, tileGridSize=(8, 8))
enhanced_r = clahe.apply(r_u8)
r_binary = cv2.adaptiveThreshold(enhanced_r, 255, cv2.ADAPTIVE_THRESH_MEAN_C, cv2.THRESH_BINARY, 21, 5)
r_binary = cv2.bitwise_and(r_binary, circle_m)

def capture_rate(alpha, th=32):
    rates = {}
    for angle_deg in [0, 45, 90, 135, 180, 225, 270, 315]:
        angle = np.radians(angle_deg)
        c = 0; t = 0
        for dist in range(int(roi_w*0.1), int(roi_w*0.48), 3):
            px = int(center_x + dist*np.cos(angle))
            py = int(center_y + dist*np.sin(angle))
            if 0 <= px < roi_w and 0 <= py < roi_h:
                t += 1
                if alpha[py,px] > th: c += 1
        rates[angle_deg] = c/t*100 if t else 0
    return rates, np.mean(list(rates.values()))

def save(name, mask):
    rates, avg = capture_rate(mask, 32)
    fg = cv2.countNonZero(mask)/(roi_w*roi_h)*100
    print(f"  {name}: fg={fg:.1f}% avg={avg:.0f}% {[f'{k}={v:.0f}%' for k,v in rates.items()]}")
    full = np.zeros((h,w), dtype=np.uint8)
    full[y0:y0+roi_h, x0:x0+roi_w] = mask
    rgba = np.dstack([img, full])
    cv2.imwrite(str(Path(f'test_output/shape_{name}.png')), rgba)

# ===== 思路：连通块过滤 =====
# 每个连通块分析：面积、外接矩形的 宽高比（aspect ratio）、填充率、骨架长度
labeled, num = ndimage.label(r_binary > 0)
print(f"R_binary 连通块数: {num}")
sizes = ndimage.sum(r_binary > 0, labeled, range(1, num + 1))
print(f"  面积分布：min={sizes.min():.0f}, max={sizes.max():.0f}, median={np.median(sizes):.0f}, sum={sizes.sum():.0f}")
# 统计每个块的形状参数
# 1. 按 min/max 维度比
boxes = []
for i in range(1, num + 1):
    ys, xs = np.where(labeled == i)
    if len(xs) < 3: continue
    wb, hb = xs.max() - xs.min() + 1, ys.max() - ys.min() + 1
    if wb <= 1 or hb <= 1: continue
    # 细长 = max(w,h) / min(w,h) 越大越细长
    aspect = max(wb, hb) / min(wb, hb)
    # 填充率 = 面积 / (w*h)
    fill = len(xs) / (wb * hb)
    boxes.append((i, len(xs), wb, hb, aspect, fill))

print(f"\n形状有效块数：{len(boxes)}")
aspects = np.array([b[4] for b in boxes])
fills = np.array([b[5] for b in boxes])
sizes_arr = np.array([b[1] for b in boxes])
print(f"  aspect: min={aspects.min():.2f}, p50={np.percentile(aspects,50):.2f}, p90={np.percentile(aspects,90):.2f}, max={aspects.max():.2f}")
print(f"  fill:   min={fills.min():.2f}, p50={np.percentile(fills,50):.2f}, p90={np.percentile(fills,90):.2f}, max={fills.max():.2f}")

# 策略 A: 大尺寸块 (与印章有关) 保留；小尺寸块只保留细/瘦的
# 印章外圆周长大概 2πr ≈ 2*3.14*(0.48*1512/2) ≈ 2280 px，宽度~5 → 面积≈11400
# 所以大的连通块 (>500 px) 很可能是笔画
# 小的块 (30-500 px) 可能是噪点 unless 细长

for big_min in [200, 300, 500, 1000]:
    for min_aspect in [1.5, 2.0, 2.5, 3.0, 4.0]:
        for max_fill in [0.5, 0.6, 0.7, 0.8]:
            # 保留条件：
            # 1. 面积 >= big_min → 大笔画直接留
            # 2. 面积 30~big_min → 必须 aspect >= min_aspect 且 fill <= max_fill (细长结构)
            # 3. 面积 < 30 → 丢掉 (噪点)
            keep_ids = set()
            for (i, sz, wb, hb, aspect, fill) in boxes:
                if sz >= big_min:
                    keep_ids.add(i)
                elif 30 <= sz < big_min:
                    if aspect >= min_aspect and fill <= max_fill:
                        keep_ids.add(i)
            if not keep_ids: continue
            keep_mask = np.isin(labeled, list(keep_ids)) & (labeled > 0)
            clean = (keep_mask.astype(np.uint8)) * 255
            clean = cv2.bitwise_or(clean, rembg_bin)  # 加 rembg 保证左半边
            clean = cv2.bitwise_and(clean, circle_m)
            r, avg = capture_rate(clean, 32)
            fg = cv2.countNonZero(clean) / (roi_w*roi_h)*100
            # 只保留 fg 20-60% 的组合，且 avg>=80
            if 20 <= fg <= 55 and avg >= 80:
                tag = f"bm{big_min}_asp{min_aspect}_fill{max_fill}"
                save(tag, clean)
