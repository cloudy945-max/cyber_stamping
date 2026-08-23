"""利用圆形几何信息 + rembg 左半边推断右半边"""
import os
import sys
import types
from pathlib import Path
import cv2
import numpy as np
from scipy import ndimage
from PIL import Image, ImageEnhance

# pymatting stub
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
cx, cy = w//2, int(h*0.55)
r = int(min(w,h)*0.25)
x0, y0, x1, y1 = max(0,cx-r), max(0,cy-r), min(w,cx+r), min(h,cy+r)
roi_bgr = img[y0:y1, x0:x1]
roi_h, roi_w = roi_bgr.shape[:2]

roi_path = Path('test_output/rembg_roi.jpg')
cv2.imwrite(str(roi_path), roi_bgr)

def capture_rate(alpha, threshold=128):
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

# 1. 加载 rembg session
session = new_session('u2netp')

# 2. 获取 rembg 蒙版（左半边完整）
print("=== Step 1: rembg 提取 ===")
with Image.open(roi_path) as pil_img:
    result = remove(pil_img, session=session)
    rembg_alpha = np.array(result)[:,:,3]
_, rembg_binary = cv2.threshold(rembg_alpha, 64, 255, cv2.THRESH_BINARY)
print(f"  rembg FG: {cv2.countNonZero(rembg_binary)/(roi_w*roi_h)*100:.1f}%")

# 3. 从 rembg 蒙版中推断圆形信息
print("\n=== Step 2: 推断圆形参数 ===")
ys, xs = np.where(rembg_binary > 0)
if len(ys) > 0:
    # 已知信息：
    # 左、下、右边界（rembg 捕获了左半边+底部+左下+右下）
    # 但右、上边界没捕获到
    left = xs.min()
    bottom = ys.max()
    right = xs.max()
    
    # 因为是圆形：已知 left 和 bottom 和右半边的部分点
    # 假设圆心在 ROI 中心附近，用已捕获点拟合圆
    # 方法：取 rembg_mask 中非零点，做最小二乘圆拟合
    pts = np.column_stack([xs, ys]).astype(np.float64)
    # 取最远的 10% 点（外圈点）
    center_x, center_y = roi_w / 2, roi_h / 2
    dists = np.sqrt((pts[:,0] - center_x)**2 + (pts[:,1] - center_y)**2)
    top_idx = np.argsort(dists)[-int(len(dists) * 0.15):]
    outer_pts = pts[top_idx]
    
    # 圆拟合 (x-a)^2 + (y-b)^2 = r^2
    # => 2ax + 2by + (r^2 - a^2 - b^2) = x^2 + y^2
    # Ax = b
    A = np.column_stack([2*outer_pts[:,0], 2*outer_pts[:,1], np.ones(len(outer_pts))])
    b = outer_pts[:,0]**2 + outer_pts[:,1]**2
    try:
        x, res, rank, s = np.linalg.lstsq(A, b, rcond=None)
        fit_cx, fit_cy = x[0], x[1]
        fit_r = np.sqrt(x[2] + fit_cx**2 + fit_cy**2)
        print(f"  Circle fit: center=({fit_cx:.0f},{fit_cy:.0f}) r={fit_r:.0f}")
        print(f"  ROI center=({roi_w//2},{roi_h//2})")
        
        # 基于圆心和半径创建圆形蒙版
        circle_mask = np.zeros((roi_h, roi_w), dtype=np.uint8)
        cv2.circle(circle_mask, (int(fit_cx), int(fit_cy)), int(fit_r * 1.0), 255, -1)
        save_diag("circlefit_mask", circle_mask)
        
        # 圆形 + 1.1 扩展
        circle_expanded = np.zeros((roi_h, roi_w), dtype=np.uint8)
        cv2.circle(circle_expanded, (int(fit_cx), int(fit_cy)), int(fit_r * 1.1), 255, -1)
        save_diag("circlefit_1.1x", circle_expanded)
        
    except Exception as e:
        print(f"  拟合失败: {e}")
        import traceback
        traceback.print_exc()
        # 用 ROI 中心和 0.45*短边 作为回退
        fit_cx, fit_cy = roi_w // 2, roi_h // 2
        fit_r = int(min(roi_w, roi_h) * 0.45)

# 4. 在圆形蒙版内用自适应阈值提取细节
print("\n=== Step 3: 圆形蒙版 + 自适应阈值 ===")
gray = cv2.cvtColor(roi_bgr, cv2.COLOR_BGR2GRAY)
clahe = cv2.createCLAHE(clipLimit=3.0, tileGridSize=(8, 8))
enhanced = clahe.apply(gray)

# 自适应阈值（多个参数组合）
configs = [
    (31, 2), (31, 3), (51, 2), (51, 3), (51, 5)
]
circle_11 = np.zeros((roi_h, roi_w), dtype=np.uint8)
cv2.circle(circle_11, (int(fit_cx), int(fit_cy)), int(fit_r * 1.1), 255, -1)

best_mask = None
best_avg = 0
for bs, c in configs:
    if bs % 2 == 0: bs += 1
    binary = cv2.adaptiveThreshold(enhanced, 255, cv2.ADAPTIVE_THRESH_MEAN_C, cv2.THRESH_BINARY_INV, bs, c)
    masked = cv2.bitwise_and(binary, circle_11)
    # 去噪
    k2 = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (2, 2))
    cleaned = cv2.morphologyEx(masked, cv2.MORPH_OPEN, k2)
    # 连通块去噪
    labeled, num = ndimage.label(cleaned > 0)
    if num > 0:
        sizes = ndimage.sum(cleaned > 0, labeled, range(1, num + 1))
        min_sz = 30
        keep = np.zeros_like(cleaned > 0, dtype=bool)
        for i in range(1, num + 1):
            if sizes[i-1] >= min_sz:
                keep = keep | (labeled == i)
        final = keep.astype(np.uint8) * 255
        rates = capture_rate(final, 32)
        avg = np.mean(list(rates.values()))
        print(f"  bs={bs} c={c}: fg={cv2.countNonZero(final)/(roi_w*roi_h)*100:.1f}% avg={avg:.0f}%")
        if avg > best_avg:
            best_avg = avg
            best_mask = final

if best_mask is not None:
    print(f"\n=== Best result (avg={best_avg:.0f}%) ===")
    save_diag("circle_best", best_mask)
