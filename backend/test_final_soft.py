"""TOP1 + Rembg 结构内部做软 alpha。
因为 TOP1 比 整个圆 更"纯净"，软 alpha 在内部的对比度会更高。"""
import sys, types
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

labeled, num = ndimage.label(r_binary > 0)
sizes = ndimage.sum(r_binary > 0, labeled, range(1, num + 1))
i_max = sizes.argmax() + 1
top1 = (labeled == i_max).astype(np.uint8) * 255
# TOP1 + rembg 是强结构蒙版
hard_mask = cv2.bitwise_or(top1, rembg_bin)

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

def save(name, alpha_u8):
    rates, avg = capture_rate(alpha_u8, 64)
    fg32 = (alpha_u8>32).sum()/(roi_w*roi_h)*100
    fg64 = (alpha_u8>64).sum()/(roi_w*roi_h)*100
    fg128 = (alpha_u8>128).sum()/(roi_w*roi_h)*100
    fg200 = (alpha_u8>200).sum()/(roi_w*roi_h)*100
    print(f"  {name}: fg32={fg32:.1f}% fg64={fg64:.1f}% fg128={fg128:.1f}% fg200={fg200:.1f}% cap64={avg:.0f}%")
    full = np.zeros((h,w), dtype=np.uint8)
    full[y0:y0+roi_h, x0:x0+roi_w] = alpha_u8
    rgba = np.dstack([img, full])
    cv2.imwrite(str(Path(f'test_output/final_{name}.png')), rgba)

# 在 hard_mask 边缘采样背景色
inner_mask = cv2.erode(hard_mask, k3, iterations=2)
edge_band = cv2.subtract(hard_mask, inner_mask)
bg_pixels = roi_bgr[edge_band > 0]
if len(bg_pixels) >= 50:
    bg_color = bg_pixels.mean(axis=0)
    print(f"硬蒙版边缘采样背景色 BGR: {bg_color}")
else:
    bg_color = np.array([180, 180, 180])

roi_f = roi_bgr.astype(np.float32)
dist_bg = np.sqrt(np.sum((roi_f - bg_color.reshape(1,1,3)) ** 2, axis=2))
gray = cv2.cvtColor(roi_bgr, cv2.COLOR_BGR2GRAY)
enhanced_g = clahe.apply(gray)
dark_raw = (255 - enhanced_g.astype(np.int32)).astype(np.float32)
red_raw = cv2.subtract(r_ch.astype(np.int16), cv2.max(g_ch, b_ch).astype(np.int16)).astype(np.float32)

# 只在 hard_mask 内部算
inside = hard_mask > 0
print(f"\nhard_mask 内部像素数: {inside.sum()}")
print(f"  内部 dist_bg: mean={dist_bg[inside].mean():.1f}, min={dist_bg[inside].min():.1f}, max={dist_bg[inside].max():.1f}")
print(f"  内部 dark_x2:  mean={(dark_raw*2)[inside].mean():.1f}")
print(f"  内部 rembg:   mean={rembg_alpha[inside].mean():.1f}")

# 最佳混合：
# - 在 rembg_bin 内部（深色印章区）：优先 rembg_alpha 原值
# - 在 top1 非 rembg 部分（右半边淡墨水）：dist_bg + dark 混合 做 SIGMOID 锐化
rembg_only = cv2.subtract(rembg_bin, top1)
top1_only = cv2.subtract(top1, rembg_bin)
overlap = cv2.bitwise_and(top1, rembg_bin)
print(f"\n分区: rembg_only={cv2.countNonZero(rembg_only)} top1_only={cv2.countNonZero(top1_only)} overlap={cv2.countNonZero(overlap)}")

# 组合：
result_alpha = np.zeros((roi_h, roi_w), dtype=np.uint8)

# 1. rembg 区域（深色、确定是印章）：保留 rembg_alpha
# rembg_alpha 已经是有语义信息的软 alpha
result_alpha = cv2.max(result_alpha, rembg_alpha)

# 2. top1_only 区域（R-G 找到的右半边淡墨水）：做 dist_bg + dark 软 alpha
# 对 top1_only 内部再做自适应，从 top1_only 边缘取背景色
top1_inner = cv2.erode(top1_only, k3, iterations=1)
top1_edge = cv2.subtract(top1_only, top1_inner)
top1_bg_pix = roi_bgr[top1_edge > 0]
if len(top1_bg_pix) >= 30:
    top1_bg = top1_bg_pix.mean(axis=0)
    print(f"  top1_only 边缘背景: {top1_bg}")
else:
    top1_bg = bg_color

# top1_only 内部做加权 + sigmoid
t1_dist = np.sqrt(np.sum((roi_f - top1_bg.reshape(1,1,3)) ** 2, axis=2))
t1_area = top1_only > 0
if t1_area.sum() > 0:
    for ds in [15, 20, 25, 30, 35]:
        for dk in [1.5, 2.0, 2.5, 3.0]:
            for wd, wdk in [(0.6,0.4),(0.7,0.3),(0.5,0.5)]:
                for sharp in [4, 6, 8, 10]:
                    for mid in [0.20, 0.25, 0.30, 0.35, 0.40]:
                        a_dist = np.clip(t1_dist / ds * 255, 0, 255)
                        a_dark = np.clip(dark_raw * dk, 0, 255)
                        soft = a_dist * wd + a_dark * wdk
                        f = soft / 255.0
                        s = 1.0 / (1.0 + np.exp(-sharp * (f - mid)))
                        u8 = (s * 255).clip(0,255).astype(np.uint8)
                        u8_t1 = cv2.bitwise_and(u8, top1_only)
                        final = cv2.max(result_alpha, u8_t1)
                        final = cv2.bitwise_and(final, circle_m)
                        r, avg64 = capture_rate(final, 64)
                        fg128 = (final>128).sum()/(roi_w*roi_h)*100
                        fg200 = (final>200).sum()/(roi_w*roi_h)*100
                        if avg64 >= 90 and fg128 <= 50:
                            save(f"t1_ds{ds}_dk{dk}_w{wd}{wdk}_sh{sharp}_m{mid}", final)

# 先跑一个 baseline: 不加 top1_only 修正，纯 rembg 原始 alpha
save("00_baseline_rembgOnly", rembg_alpha)
# 加上 coarse mask (rembg 膨胀填充) 后的区域，但原始 rembg alpha
coarse_raw = cv2.bitwise_or(rembg_bin, r_binary)
coarse_raw = cv2.bitwise_and(coarse_raw, circle_m)
dilated = cv2.dilate(coarse_raw, k3, iterations=6)
filled = ndimage.binary_fill_holes(dilated > 0).astype(np.uint8) * 255
coarse_mask = cv2.dilate(filled, k3, iterations=2)
rmbg_in_coarse = cv2.bitwise_and(rembg_alpha, coarse_mask)
save("01_rembgAlphaCoarseMasked", rmbg_in_coarse)
# 软 alpha (之前正式代码的版本) 但这次基于 hard_mask
save("02_hardmask_binary", hard_mask)
