"""直接查看最大的几个连通块，理解 R-G 结果结构"""
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

def save(name, mask):
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
    r, avg = capture_rate(mask, 32)
    fg = cv2.countNonZero(mask)/(roi_w*roi_h)*100
    print(f"  {name}: fg={fg:.1f}% avg={avg:.0f}% {[f'{k}={v:.0f}%' for k,v in r.items()]}")
    full = np.zeros((h,w), dtype=np.uint8)
    full[y0:y0+roi_h, x0:x0+roi_w] = mask
    rgba = np.dstack([img, full])
    cv2.imwrite(str(Path(f'test_output/topcc_{name}.png')), rgba)

# Top 15 连通块单独看
top_idx = np.argsort(-sizes)[:15]
print("Top 15 连通块：")
for rank, idx in enumerate(top_idx, 1):
    i = idx + 1
    sz = sizes[idx]
    cc = (labeled == i).astype(np.uint8) * 255
    ys, xs = np.where(cc > 0)
    if len(xs) == 0:
        continue
    wb, hb = xs.max() - xs.min() + 1, ys.max() - ys.min() + 1
    aspect = max(wb,hb)/min(wb,hb) if min(wb,hb)>0 else 0
    fill = len(xs)/(wb*hb)
    print(f"  #{rank}: id={i} sz={sz:.0f} box={wb}x{hb} aspect={aspect:.2f} fill={fill:.2f}")

# Top 1 单独
i_max = sizes.argmax() + 1
cc1 = (labeled == i_max).astype(np.uint8) * 255
save(f"TOP1_id{i_max}_sz{sizes[i_max-1]:.0f}", cc1)

# Top 1 + rembg
save(f"TOP1_plus_rembg", cv2.bitwise_or(cc1, rembg_bin))

# Top 5 合并
top5_mask = np.zeros_like(r_binary)
for idx in top_idx[:5]:
    top5_mask[labeled == idx+1] = 255
save("TOP5", top5_mask)

# Top 5 + rembg
save("TOP5_plus_rembg", cv2.bitwise_or(top5_mask, rembg_bin))

# Top 10 合并
top10_mask = np.zeros_like(r_binary)
for idx in top_idx[:10]:
    top10_mask[labeled == idx+1] = 255
save("TOP10", top10_mask)

# 所有 >= 200 的合并
big_mask = np.zeros_like(r_binary)
for i in range(1, num+1):
    if sizes[i-1] >= 200:
        big_mask[labeled == i] = 255
save(f"BIG_ge_200_n{(sizes>=200).sum()}", big_mask)

# 所有 >= 1000 的合并
big1k_mask = np.zeros_like(r_binary)
for i in range(1, num+1):
    if sizes[i-1] >= 1000:
        big1k_mask[labeled == i] = 255
save(f"BIG_ge_1000_n{(sizes>=1000).sum()}", big1k_mask)

# 关键方案：最大连通块内部，做"腐蚀-重建"只保留真实笔画
# 最大块里既有笔画也有大块填充物（来自圆内背景被自适应阈值二值化）
# 做开运算 + 距离变换 + 重建
print("\n最大块内部精细处理：")
# 对 TOP1 做：开运算(小核) 去掉大斑点里的厚部分，只保留细线条
for open_k in [2, 3, 4]:
    for open_iter in [1, 2, 3]:
        kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (open_k, open_k))
        opened = cv2.morphologyEx(cc1, cv2.MORPH_OPEN, kernel, iterations=open_iter)
        # 再 dilate 回一点
        closed = cv2.dilate(opened, kernel, iterations=open_iter)
        combined = cv2.bitwise_or(closed, rembg_bin)
        save(f"TOP1_open{open_k}x{open_iter}_plusRemBg", combined)

# 对 TOP1 做形态学细化（骨架化）
def skeletonize(mask):
    skel = np.zeros_like(mask)
    size = np.size(mask)
    elem = cv2.getStructuringElement(cv2.MORPH_CROSS, (3,3))
    m = mask.copy()
    while True:
        eroded = cv2.erode(m, elem)
        temp = cv2.dilate(eroded, elem)
        temp = cv2.subtract(m, temp)
        skel = cv2.bitwise_or(skel, temp)
        m = eroded.copy()
        if cv2.countNonZero(m) == 0:
            break
    return skel

skel = skeletonize(cc1)
# 骨架膨胀 2 像素，保证笔画宽度
skel_dil = cv2.dilate(skel, k3, iterations=2)
save("TOP1_skeleton_dil2", cv2.bitwise_or(skel_dil, rembg_bin))
skel_dil3 = cv2.dilate(skel, k3, iterations=3)
save("TOP1_skeleton_dil3", cv2.bitwise_or(skel_dil3, rembg_bin))

# 对 BIG_ge_1000 做骨架膨胀
skel_big = skeletonize(big1k_mask)
for dil in [1,2,3,4]:
    skel_d = cv2.dilate(skel_big, k3, iterations=dil)
    save(f"BIG1k_skeleton_dil{dil}", cv2.bitwise_or(skel_d, rembg_bin))
