"""测试 rembg 改进方案"""
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

def save_diag(name, alpha):
    fg_32 = cv2.countNonZero(alpha > 32)
    fg_64 = cv2.countNonZero(alpha > 64)
    fg_128 = cv2.countNonZero(alpha > 128)
    rates_32 = capture_rate(alpha, 32)
    rates_64 = capture_rate(alpha, 64)
    rates_128 = capture_rate(alpha, 128)
    avg_128 = np.mean(list(rates_128.values()))
    print(f"  [{name}] fg32={fg_32/(roi_w*roi_h)*100:.1f}% fg64={fg_64/(roi_w*roi_h)*100:.1f}% fg128={fg_128/(roi_w*roi_h)*100:.1f}% avgRate128={avg_128:.0f}%")
    print(f"     Rate128: {[f'{k}={v:.0f}%' for k,v in rates_128.items()]}")
    cv2.imwrite(str(Path(f'test_output/diag_{name}_alpha.png')), alpha)
    full_mask = np.zeros((h, w), dtype=np.uint8)
    full_mask[y0:y0+roi_h, x0:x0+roi_w] = alpha
    rgba = np.dstack([img, full_mask])
    cv2.imwrite(str(Path(f'test_output/diag_{name}_rgba.png')), rgba)
    return rates_128

# 加载 session
session = new_session('u2netp')
print(f"Session: u2netp loaded")

# 方案 A: 原始
print("\n=== A: 原始 rembg ===")
with Image.open(roi_path) as pil_img:
    result = remove(pil_img, session=session)
    alpha_raw = np.array(result)[:,:,3]
    save_diag("A_raw", alpha_raw)

# 方案 B: 降低阈值 (alpha > 32)
print("\n=== B: rembg alpha > 32 (低阈值) ===")
# 用原始 alpha，但阈值改为 32
alpha_lo = (alpha_raw > 32).astype(np.uint8) * 255
save_diag("B_lowthresh", alpha_lo)

# 方案 C: CLAHE 增强对比度后再 rembg
print("\n=== C: CLAHE 增强后 rembg ===")
roi_pil_enh = Image.fromarray(cv2.cvtColor(roi_bgr, cv2.COLOR_BGR2RGB))
# PIL 对比度增强
for contrast in [1.5, 2.0, 3.0]:
    enhancer = ImageEnhance.Contrast(roi_pil_enh)
    enhanced_pil = enhancer.enhance(contrast)
    enhanced_path = Path(f'test_output/enhanced_c{contrast}.jpg')
    enhanced_pil.save(enhanced_path)
    result = remove(enhanced_pil, session=session)
    alpha = np.array(result)[:,:,3]
    save_diag(f"C_contrast_{contrast}", alpha)

# 方案 D: CLAHE + 低阈值
print("\n=== D: CLAHE 2.0 + alpha>32 ===")
enhancer = ImageEnhance.Contrast(roi_pil_enh)
enhanced_pil = enhancer.enhance(2.0)
result = remove(enhanced_pil, session=session)
alpha = np.array(result)[:,:,3]
alpha_lo = (alpha > 32).astype(np.uint8) * 255
save_diag("D_c2_lo32", alpha_lo)

# 方案 E: 更大的 rembg 模型（如果有）
u2net_home = Path(os.environ.get('U2NET_HOME') or os.path.expanduser('~/.u2net'))
print(f"\n=== Model files available ===")
for f in sorted(u2net_home.iterdir()):
    print(f"  {f.name}: {f.stat().st_size/1024/1024:.1f} MB")
    model_name = f.stem
    if model_name != 'u2netp' and f.suffix == '.onnx':
        try:
            print(f"\n=== E: 测试模型 {model_name} ===")
            session2 = new_session(model_name)
            result = remove(enhanced_pil, session=session2)
            alpha = np.array(result)[:,:,3]
            save_diag(f"E_{model_name}", alpha)
            alpha_lo = (alpha > 32).astype(np.uint8) * 255
            save_diag(f"E_{model_name}_lo32", alpha_lo)
        except Exception as e:
            print(f"  模型 {model_name} 加载失败: {e}")
