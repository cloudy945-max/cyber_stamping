"""直接测试 rembg 在完整印章 ROI 上的效果"""
import sys, types
from pathlib import Path
import cv2
import numpy as np
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

src = Path(r'test_output/module_test/8181.jpg')
img = cv2.imread(str(src))
h, w = img.shape[:2]

# 印章 ROI
stamp_cx, stamp_cy = w // 2, int(h * 0.55)
stamp_r = int(min(w, h) * 0.17)

roi_x0 = max(0, stamp_cx - stamp_r)
roi_y0 = max(0, stamp_cy - stamp_r)
roi_x1 = min(w, stamp_cx + stamp_r)
roi_y1 = min(h, stamp_cy + stamp_r)
roi = img[roi_y0:roi_y1, roi_x0:roi_x1]
rh, rw = roi.shape[:2]
print(f"ROI: {rw}x{rh}")

# 圆形蒙版
cy, cx = rh//2, rw//2
circle_r = int(min(rw, rh) * 0.98)
circle_mask = np.zeros((rh, rw), dtype=np.uint8)
cv2.circle(circle_mask, (cx, cy), circle_r, 255, -1)

# rembg 处理 ROI
print("Running rembg on ROI...")
session = new_session('u2netp')
pil_img = Image.fromarray(cv2.cvtColor(roi, cv2.COLOR_BGR2RGB))
result = remove(pil_img, session=session)
arr = np.array(result)
print(f"rembg output shape: {arr.shape}, mode: {result.mode}")

if arr.shape[2] == 4:
    rembg_alpha = arr[:, :, 3]
else:
    rembg_alpha = np.full((rh, rw), 255, dtype=np.uint8)

# 限制在圆形内
rembg_in_circle = cv2.bitwise_and(rembg_alpha, circle_mask)

# 保存
rgba = np.dstack([roi, rembg_in_circle])
cv2.imwrite("test_output/rembg_roi_result.png", rgba)

# 分析
print(f"\nrembg alpha 统计 (圆形内):")
in_circle = circle_mask > 0
alpha_in = rembg_alpha[in_circle]
print(f"  min={alpha_in.min()}, max={alpha_in.max()}, mean={alpha_in.mean():.1f}")
print(f"  alpha>128: {(alpha_in>128).sum()/alpha_in.size*100:.1f}%")
print(f"  alpha>200: {(alpha_in>200).sum()/alpha_in.size*100:.1f}%")

# 8 方向捕获率
print(f"\n8方向捕获率 (rembg alpha):")
for th in [32, 64, 128, 200]:
    rates = {}
    for ang in [0, 45, 90, 135, 180, 225, 270, 315]:
        a = np.radians(ang)
        c = 0; t = 0
        for d in range(int(min(rw,rh)*0.2), int(min(rw,rh)*0.48), 3):
            px = int(cx + d*np.cos(a))
            py = int(cy + d*np.sin(a))
            if 0<=px<rw and 0<=py<rh:
                t += 1
                if rembg_alpha[py,px] > th: c += 1
        rates[ang] = c/t*100 if t else 0
    avg = np.mean(list(rates.values()))
    print(f"  th={th:3d}: avg={avg:.0f}% {[f'{k}={v:.0f}%' for k,v in rates.items()]}")

# 对比：rembg vs R-G
b_r, g_r, r_r = cv2.split(roi)
rg = (r_r.astype(np.int16) - g_r.astype(np.int16)).clip(0, 255).astype(np.uint8)
# 在圆形内的 RG 值
rg_in = rg[in_circle]
print(f"\nR-G 在圆形内: min={rg_in.min()}, max={rg_in.max()}, mean={rg_in.mean():.1f}")

# 保存 rembg alpha 单独查看
cv2.imwrite("test_output/rembg_alpha_only.png", rembg_alpha)
