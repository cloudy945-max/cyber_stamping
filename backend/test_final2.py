"""重新调整 soft alpha 搜索，放宽条件并打印中间结果"""
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
    cv2.imwrite(str(Path(f'test_output/final2_{name}.png')), rgba)

top1_inner = cv2.erode(top1, k3, iterations=1)
top1_edge = cv2.subtract(top1, top1_inner)
top1_bg_pix = roi_bgr[top1_edge > 0]
top1_bg = top1_bg_pix.mean(axis=0) if len(top1_bg_pix) >= 30 else np.array([150,150,150])
print(f"top1 边缘背景 BGR: {top1_bg}")

roi_f = roi_bgr.astype(np.float32)
t1_dist = np.sqrt(np.sum((roi_f - top1_bg.reshape(1,1,3)) ** 2, axis=2))
gray = cv2.cvtColor(roi_bgr, cv2.COLOR_BGR2GRAY)
enhanced_g = clahe.apply(gray)
dark_raw = (255 - enhanced_g.astype(np.int32)).astype(np.float32)
red_raw = cv2.subtract(r_ch.astype(np.int16), cv2.max(g_ch, b_ch).astype(np.int16)).astype(np.float32)

# 先用最简单的线性映射：不做 sigmoid，只用 hard_mask * normalized_value
t1_area = top1 > 0
print(f"\ntop1_only 区域统计：")
print(f"  dist_bg: mean={t1_dist[t1_area].mean():.1f}, std={t1_dist[t1_area].std():.1f}, p20={np.percentile(t1_dist[t1_area],20):.1f}, p80={np.percentile(t1_dist[t1_area],80):.1f}")
print(f"  dark_raw*2: mean={(dark_raw*2)[t1_area].mean():.1f}")
print(f"  red_raw*6:  mean={(red_raw*6)[t1_area].mean():.1f}")

# 直接线性归一化：不 sigmoid，让背景自然有低 alpha
best_list = []
idx = 0
for ds in [25, 35, 45, 60, 80]:
    for dk in [1.5, 2.0, 2.5]:
        for rk in [3, 5, 7]:
            for wd, wdk, wr in [(0.4,0.4,0.2),(0.5,0.3,0.2),(0.3,0.4,0.3)]:
                # 线性组合
                a_dist = np.clip(t1_dist / ds * 255, 0, 255).astype(np.float32)
                a_dark = np.clip(dark_raw * dk, 0, 255)
                a_red = np.clip(red_raw * rk, 0, 255)
                soft = a_dist * wd + a_dark * wdk + a_red * wr
                u8 = np.clip(soft, 0, 255).astype(np.uint8)
                u8_t1 = cv2.bitwise_and(u8, top1)
                final = cv2.max(rembg_alpha, u8_t1)
                final = cv2.bitwise_and(final, circle_m)
                r, avg64 = capture_rate(final, 64)
                fg32 = (final>32).sum()/(roi_w*roi_h)*100
                fg64 = (final>64).sum()/(roi_w*roi_h)*100
                fg128 = (final>128).sum()/(roi_w*roi_h)*100
                fg200 = (final>200).sum()/(roi_w*roi_h)*100
                # 目标：cap64 >= 90%，fg128 < 70%，fg200 尽可能高
                if avg64 >= 88 and fg128 <= 70 and fg200 >= 30:
                    score = avg64 * 10 + fg200 - fg128
                    best_list.append((score, idx, ds, dk, rk, wd,wdk,wr, final.copy(), avg64, fg64, fg128, fg200, r))
                idx += 1

best_list.sort(key=lambda x: -x[0])
print(f"\nBest {len(best_list)} 个线性组合：")
for rank, (score, i, ds, dk, rk, wd,wdk,wr, u8, avg64, fg64, fg128, fg200, r) in enumerate(best_list[:10], 1):
    print(f"  #{rank} score={score:.1f} ds={ds} dk={dk} rk={rk} w=({wd},{wdk},{wr})")
    print(f"        fg64={fg64:.1f}% fg128={fg128:.1f}% fg200={fg200:.1f}% cap64={avg64:.0f}%")
    print(f"        8d: {[f'{k}={v:.0f}%' for k,v in r.items()]}")
    save(f"BEST_R{rank}_sc{score:.0f}", u8)

# Baseline: 直接用 rembg_alpha 覆盖 top1（不是 max，而是直接覆盖！）
# 就是 "rembg 左半边 + top1 右半边 但 top1 区域 alpha 用软值"
# 这个 baseline 就是我之前写的正式代码
base = rembg_alpha.copy()
# 把 top1 区域里 alpha < 128 的地方，换成 dist_bg*dark 混合
weak_in_top1 = (rembg_alpha < 128) & (top1 > 0)
print(f"\nBaseline: top1 区域 rembg_alpha < 128 的像素: {weak_in_top1.sum()}")
# 对这些弱像素填入 a_dist * 0.5 + dark * 0.3 + red * 0.2（线性）
ad = np.clip(t1_dist / 55 * 255, 0, 255).astype(np.float32)
ak = np.clip(dark_raw * 2, 0, 255)
ar = np.clip(red_raw * 6, 0, 255)
blend = (ad * 0.5 + ak * 0.3 + ar * 0.2).astype(np.uint8)
rembg_copy = rembg_alpha.copy()
rembg_copy[weak_in_top1] = blend[weak_in_top1]
rembg_copy = cv2.bitwise_and(rembg_copy, circle_m)
save("BASELINE_weakFill_linear", rembg_copy)

# 对 baseline 做 sigmoid 锐化，看看效果
for sharp in [4, 6, 8]:
    for mid in [0.35, 0.45, 0.55]:
        f = rembg_copy.astype(np.float32) / 255.0
        s = 1.0 / (1.0 + np.exp(-sharp * (f - mid)))
        u8 = (s * 255).clip(0, 255).astype(np.uint8)
        r, avg64 = capture_rate(u8, 64)
        fg128 = (u8>128).sum()/(roi_w*roi_h)*100
        if avg64 >= 85:
            save(f"BASELINE_sharp{sharp}_m{mid}", u8)
