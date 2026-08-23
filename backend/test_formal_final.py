"""调用正式 segment_stamp 函数端到端测试 8181.jpg"""
import sys, types
from pathlib import Path
import cv2
import numpy as np

sys.path.insert(0, str(Path(__file__).parent))
sys.path.insert(0, str(Path(__file__).parent / "app"))

# pymatting stub 注入（与 background_removal 一样）
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

from app.services.stamp_segment import segment_stamp

src = Path(r"test_output/module_test/8181.jpg")
out = Path(r"test_output/8181_FINAL_FORMAL.png")

img = cv2.imread(str(src))
h, w = img.shape[:2]
r = int(min(w, h) * 0.25)
cx, cy = w // 2, int(h * 0.55)
bbox = (cx - r, cy - r, cx + r, cy + r)
print(f"bbox: {bbox}, roi size: {2*r}x{2*r}")

result = segment_stamp(src, out, bbox=bbox, color="auto")
print(f"segment_stamp 返回: {result}")

if result and result.exists():
    rgba = cv2.imread(str(result), cv2.IMREAD_UNCHANGED)
    alpha = rgba[:,:,3]
    print(f"Alpha 统计 (全图):")
    print(f"  max={alpha.max()}")
    print(f"  fg>10:  {(alpha>10).sum()/alpha.size*100:.1f}%")
    print(f"  fg>64:  {(alpha>64).sum()/alpha.size*100:.1f}%")
    print(f"  fg>128: {(alpha>128).sum()/alpha.size*100:.1f}%")
    print(f"  fg>200: {(alpha>200).sum()/alpha.size*100:.1f}%")

    # ROI 内 8 方向捕获率
    x0, y0, x1, y1 = bbox
    roi_a = alpha[y0:y1, x0:x1]
    rh, rw = roi_a.shape[:2]
    cc, cyy = rw//2, rh//2
    print(f"\nROI 8 方向捕获率 (alpha>64):")
    for th in [32, 64, 128, 200]:
        rates = {}
        for ang in [0,45,90,135,180,225,270,315]:
            a = np.radians(ang)
            c=0; t=0
            for d in range(int(rw*0.1), int(rw*0.48), 3):
                px = int(cc + d*np.cos(a))
                py = int(cyy + d*np.sin(a))
                if 0<=px<rw and 0<=py<rh:
                    t+=1
                    if roi_a[py,px]>th: c+=1
            rates[ang] = c/t*100 if t else 0
        avg = np.mean(list(rates.values()))
        print(f"  th={th:3d}: avg={avg:.0f}% {[f'{k}={v:.0f}%' for k,v in rates.items()]}")

    print(f"\n最终文件: {out.resolve()}")
