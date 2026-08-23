"""用正式的 segment_stamp 函数测试 8181.jpg 效果。"""
import sys, types
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))
sys.path.insert(0, str(Path(__file__).parent / "app"))

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
import cv2
import numpy as np

src = Path(r"test_output/module_test/8181.jpg")
out = Path(r"test_output/8181_stamp_softalpha.png")

# bbox 参考之前：中心 (w//2, h*0.55)，半径=min(w,h)*0.25
img = cv2.imread(str(src))
h, w = img.shape[:2]
r = int(min(w, h) * 0.25)
cx, cy = w // 2, int(h * 0.55)
bbox = (cx - r, cy - r, cx + r, cy + r)

result = segment_stamp(src, out, bbox=bbox, color="auto")
print(f"结果：{result}")

if result and result.exists():
    # 简单统计 alpha
    rgba = cv2.imread(str(result), cv2.IMREAD_UNCHANGED)
    if rgba.shape[2] == 4:
        alpha = rgba[:,:,3]
        fg = (alpha > 10).sum() / alpha.size * 100
        strong = (alpha > 200).sum() / alpha.size * 100
        medium = ((alpha > 64) & (alpha <= 200)).sum() / alpha.size * 100
        weak = ((alpha > 10) & (alpha <= 64)).sum() / alpha.size * 100
        print(f"alpha 分布：强(>200)={strong:.1f}%, 中(64-200)={medium:.1f}%, 弱(10-64)={weak:.1f}%, 总fg={fg:.1f}%")
        print("  检查 alpha 通道...")
        cv2.imwrite("test_output/8181_alpha_channel.png", alpha)
        print("  alpha 通道图已保存")
