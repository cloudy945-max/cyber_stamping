"""诊断 rembg 模型加载与效果"""
import os
import sys
from pathlib import Path

# 1. 模型文件检查
u2net_home = os.environ.get('U2NET_HOME') or os.path.join(os.path.expanduser('~'), '.u2net')
model_name = 'u2netp'
model_path = Path(u2net_home) / f'{model_name}.onnx'

print(f"[1] 模型文件检查:")
print(f"    U2NET_HOME: {u2net_home}")
print(f"    Model name: {model_name}")
print(f"    Model path: {model_path}")
print(f"    File exists: {model_path.exists()}")
if model_path.exists():
    print(f"    File size: {model_path.stat().st_size / 1024 / 1024:.1f} MB")

# 2. rembg 导入检查
print(f"\n[2] rembg 导入检查:")
try:
    # 注入 pymatting stubs
    import types
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
            if "." in name:
                mod.__path__ = []
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
    print(f"    rembg imported OK")
except Exception as e:
    print(f"    rembg import FAILED: {e}")
    import traceback
    traceback.print_exc()
    sys.exit(1)

# 3. Session 加载
print(f"\n[3] Session 加载:")
try:
    session = new_session(model_name)
    print(f"    Session loaded OK: {type(session).__name__}")
except Exception as e:
    print(f"    Session load FAILED: {e}")
    import traceback
    traceback.print_exc()
    sys.exit(1)

# 4. 读取测试图片
print(f"\n[4] 图片处理:")
src = Path(r'd:\projects\cyber_stamping\backend\test_output\module_test\8181.jpg')
import cv2
import numpy as np
from scipy import ndimage

img = cv2.imread(str(src))
h, w = img.shape[:2]
print(f"    Image size: {w}x{h}")

# ROI
cx, cy = w//2, int(h*0.55)
r = int(min(w,h)*0.25)
x0, y0, x1, y1 = max(0,cx-r), max(0,cy-r), min(w,cx+r), min(h,cy+r)
roi_bgr = img[y0:y1, x0:x1]
roi_h, roi_w = roi_bgr.shape[:2]
print(f"    ROI size: {roi_w}x{roi_h}")

# 保存 ROI 为临时 jpg 用 PIL 读
roi_path = Path('test_output/rembg_roi.jpg')
cv2.imwrite(str(roi_path), roi_bgr)

# 5. 用 PIL 方式调用 rembg（和 background_removal.py 一致）
print(f"\n[5] rembg 处理 (PIL 方式):")
from PIL import Image
with Image.open(roi_path) as pil_img:
    print(f"    PIL image: {pil_img.size}, mode={pil_img.mode}")
    result = remove(pil_img, session=session)
    print(f"    rembg output: size={result.size}, mode={result.mode}")

    if result.mode == 'RGBA':
        arr = np.array(result)
        alpha = arr[:,:,3]
        fg = cv2.countNonZero(alpha > 128)
        print(f"    Alpha FG (>128): {fg} ({fg/(roi_w*roi_h)*100:.1f}%)")
        print(f"    Alpha mean: {alpha.mean():.1f}")
        print(f"    Alpha min/max: {alpha.min()}/{alpha.max()}")
        print(f"    Alpha >0: {cv2.countNonZero(alpha > 0)} ({cv2.countNonZero(alpha > 0)/(roi_w*roi_h)*100:.1f}%)")

        # 保存 alpha
        cv2.imwrite(str(Path('test_output/diag_rembg_alpha.png')), alpha)
        # 保存 rgba
        cv2.imwrite(str(Path('test_output/diag_rembg_rgba.png')), cv2.cvtColor(arr, cv2.COLOR_RGBA2BGRA))

        # 8方向捕获率
        center_x, center_y = roi_w // 2, roi_h // 2
        print(f"    8方向捕获率 (alpha>128):")
        for angle_deg in [0, 45, 90, 135, 180, 225, 270, 315]:
            angle = np.radians(angle_deg)
            captured = 0
            total = 0
            for dist in range(int(roi_w * 0.1), int(roi_w * 0.48), 3):
                px_x = int(center_x + dist * np.cos(angle))
                px_y = int(center_y + dist * np.sin(angle))
                if 0 <= px_x < roi_w and 0 <= px_y < roi_h:
                    total += 1
                    if alpha[px_y, px_x] > 128:
                        captured += 1
            pct = captured / total * 100 if total > 0 else 0
            print(f"      Angle {angle_deg}: {pct:.0f}% ({captured}/{total})")

# 6. 对比：用 numpy array 方式直接调用
print(f"\n[6] rembg 处理 (numpy BGR 方式):")
try:
    result2 = remove(roi_bgr, session=session)
    if isinstance(result2, np.ndarray):
        print(f"    Output shape: {result2.shape}, dtype={result2.dtype}")
        if result2.shape[2] == 4:
            alpha2 = result2[:,:,3]
            fg2 = cv2.countNonZero(alpha2 > 128)
            print(f"    Alpha FG (>128): {fg2} ({fg2/(roi_w*roi_h)*100:.1f}%)")
            cv2.imwrite(str(Path('test_output/diag_rembg_np_alpha.png')), alpha2)
except Exception as e:
    print(f"    Numpy mode FAILED: {e}")

# 7. 自适应阈值对比
print(f"\n[7] 自适应阈值对比:")
gray = cv2.cvtColor(roi_bgr, cv2.COLOR_BGR2GRAY)
clahe = cv2.createCLAHE(clipLimit=3.0, tileGridSize=(8, 8))
enhanced = clahe.apply(gray)
block_size = 51
adapt_binary = cv2.adaptiveThreshold(enhanced, 255, cv2.ADAPTIVE_THRESH_MEAN_C,
                                       cv2.THRESH_BINARY_INV, block_size, 5)
print(f"    Adaptive: {cv2.countNonZero(adapt_binary)} ({cv2.countNonZero(adapt_binary)/(roi_w*roi_h)*100:.1f}%)")
cv2.imwrite(str(Path('test_output/diag_adapt.png')), adapt_binary)

center_x, center_y = roi_w // 2, roi_h // 2
print(f"    8方向捕获率:")
for angle_deg in [0, 45, 90, 135, 180, 225, 270, 315]:
    angle = np.radians(angle_deg)
    captured = 0
    total = 0
    for dist in range(int(roi_w * 0.1), int(roi_w * 0.48), 3):
        px_x = int(center_x + dist * np.cos(angle))
        px_y = int(center_y + dist * np.sin(angle))
        if 0 <= px_x < roi_w and 0 <= px_y < roi_h:
            total += 1
            if adapt_binary[px_y, px_x] > 0:
                captured += 1
    pct = captured / total * 100 if total > 0 else 0
    print(f"      Angle {angle_deg}: {pct:.0f}% ({captured}/{total})")

print("\n诊断完成。")
