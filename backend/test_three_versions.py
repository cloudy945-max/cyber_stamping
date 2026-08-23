"""生成三个版本的印章分割结果对比：
v_current:  当前参数（距离阈值30, R-G下限3）
v_improved: 更激进去除纸张（距离阈值15, R-G下限5）
v_faded:    当前alpha分布 + 染色部分红色调淡
"""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import cv2
import numpy as np
from PIL import Image
from app.services.stamp_segment import _get_rembg_session

SRC = r'd:\projects\cyber_stamping\backend\test_output\module_test\8181.jpg'
OUT_DIR = r'd:\projects\cyber_stamping\backend\test_output\api_test'

def run_segment(src_path, dst_path, dist_threshold=30, rg_light_lower=3, fade_light=False):
    """运行分割算法，可调参数：距离阈值、R-G淡墨水下限、是否调淡染色"""
    img_bgr = cv2.imread(src_path)
    if img_bgr is None:
        from PIL import Image as PILImage
        pil = PILImage.open(src_path).convert('RGB')
        img_bgr = cv2.cvtColor(np.array(pil), cv2.COLOR_RGB2BGR)
    H, W = img_bgr.shape[:2]
    k3 = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (3, 3))

    # 圆形定位
    b_ch, g_ch, r_ch = cv2.split(img_bgr)
    r_minus_g = (r_ch.astype(np.int16) - g_ch.astype(np.int16)).clip(0, 255).astype(np.uint8)
    _, r_binary = cv2.threshold(r_minus_g, 10, 255, cv2.THRESH_BINARY)
    r_dilated = cv2.dilate(r_binary, k3, iterations=3)
    contours, _ = cv2.findContours(r_dilated, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    contours = sorted(contours, key=cv2.contourArea, reverse=True)
    stamp_cx, stamp_cy, stamp_r = None, None, None
    for cnt in contours[:20]:
        area = cv2.contourArea(cnt)
        if area < 50000: continue
        x, y, cw, ch = cv2.boundingRect(cnt)
        aspect = cw / ch if ch > 0 else 0
        if 0.7 < aspect < 1.4:
            stamp_cx = x + cw // 2; stamp_cy = y + ch // 2; stamp_r = max(cw, ch) // 2; break
    if stamp_cx is None:
        stamp_cx, stamp_cy = W // 2, H // 2; stamp_r = int(min(W, H) * 0.48)

    # ROI
    roi_w = int(stamp_r * 2.2); roi_h = int(stamp_r * 2.2)
    bx0 = max(0, stamp_cx - roi_w // 2); by0 = max(0, stamp_cy - roi_h // 2)
    bx1 = min(W, bx0 + roi_w); by1 = min(H, by0 + roi_h)
    roi_w = bx1 - bx0; roi_h = by1 - by0
    roi = img_bgr[by0:by1, bx0:bx1].copy()
    b_roi, g_roi, r_roi = cv2.split(roi)
    rg = (r_roi.astype(np.int16) - g_roi.astype(np.int16)).clip(0, 255).astype(np.uint8)
    rg_i16 = rg.astype(np.int16)

    # rembg
    rembg_alpha_roi = np.zeros((roi_h, roi_w), dtype=np.uint8)
    session = _get_rembg_session()
    if session is not None:
        try:
            from rembg import remove
            pil_img = Image.fromarray(cv2.cvtColor(roi, cv2.COLOR_BGR2RGB))
            result = remove(pil_img, session=session)
            arr = np.array(result)
            if arr.shape[2] == 4:
                rembg_alpha_roi = arr[:, :, 3]
        except: pass

    # seal_mask
    rcx, rcy, rr = stamp_cx - bx0, stamp_cy - by0, stamp_r
    Y, X = np.mgrid[0:roi_h, 0:roi_w]
    dist_roi = np.sqrt((X - rcx)**2 + (Y - rcy)**2)
    search_r = int(rr * 1.35)
    search_mask = (dist_roi <= search_r).astype(np.uint8) * 255
    _, ink_bin = cv2.threshold(rg, 3, 255, cv2.THRESH_BINARY)
    ink_bin = cv2.morphologyEx(ink_bin, cv2.MORPH_CLOSE, k3, iterations=3)
    ink_in_s = cv2.bitwise_and(ink_bin, search_mask)
    nlab, labels, stats, _ = cv2.connectedComponentsWithStats(ink_in_s, connectivity=8)
    seal_mask = np.zeros((roi_h, roi_w), dtype=np.uint8)
    if nlab > 1:
        largest = np.argmax(stats[1:, cv2.CC_STAT_AREA]) + 1
        seal_mask = (labels == largest).astype(np.uint8) * 255
        k5d = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (5, 5))
        k3o = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (3, 3))
        seal_mask = cv2.dilate(seal_mask, k5d, iterations=2)
        seal_mask = cv2.morphologyEx(seal_mask, cv2.MORPH_OPEN, k3o, iterations=1)

    # 分层 alpha（使用可调参数 rg_light_lower）
    final_alpha = np.zeros((roi_h, roi_w), dtype=np.uint8)
    final_alpha[(rg_i16 > 15) & (seal_mask > 0)] = 255
    final_alpha[(rg_i16 > 8) & (rg_i16 <= 15) & (seal_mask > 0)] = 200
    final_alpha[(rg_i16 > rg_light_lower) & (rg_i16 <= 8) & (seal_mask > 0)] = 120

    # 形态学清理
    final_alpha = cv2.morphologyEx(final_alpha, cv2.MORPH_CLOSE, k3, iterations=2)
    final_alpha = cv2.morphologyEx(final_alpha, cv2.MORPH_OPEN, k3, iterations=1)
    final_alpha[seal_mask == 0] = 0

    # 主连通域过滤
    _, abin = cv2.threshold(final_alpha, 63, 255, cv2.THRESH_BINARY)
    ncc, cc, cc_stats, _ = cv2.connectedComponentsWithStats(abin, connectivity=8)
    if ncc > 1:
        areas = cc_stats[1:, cv2.CC_STAT_AREA]
        largest = np.argmax(areas) + 1
        max_area = areas[largest - 1]
        keep = np.zeros_like(cc, dtype=bool)
        for i in range(1, ncc):
            if cc_stats[i, cv2.CC_STAT_AREA] >= max_area * 0.5:
                keep |= cc == i
        final_alpha[~keep & (final_alpha >= 64)] = 0

    # 距离阈值过滤（使用可调参数 dist_threshold）
    strong_mask = (final_alpha >= 200).astype(np.uint8) * 255
    if strong_mask.sum() > 0:
        dist_map = cv2.distanceTransform(255 - strong_mask, cv2.DIST_L1, 3)
        light = (final_alpha >= 64) & (final_alpha < 200)
        final_alpha[light & (dist_map > float(dist_threshold))] = 0

    # 还原到全图
    full_alpha = np.zeros((H, W), dtype=np.uint8)
    full_alpha[by0:by0 + roi_h, bx0:bx0 + roi_w] = final_alpha

    # 颜色校正
    output_bgr = img_bgr.copy()
    ink_mask = full_alpha >= 64
    full_alpha[full_alpha < 64] = 0
    output_bgr[full_alpha < 64] = [0, 0, 0]

    if ink_mask.sum() > 0:
        full_hsv = cv2.cvtColor(output_bgr, cv2.COLOR_BGR2HSV)
        ink_pix = full_hsv[ink_mask].astype(np.float32)
        h_new = np.full(ink_pix.shape[0], 172.0, dtype=np.float32)
        s_orig = ink_pix[:, 1]
        s_new = 130.0 + (s_orig - s_orig.mean()) * 1.5
        s_new = np.clip(s_new, 60, 255)
        v_new = ink_pix[:, 2]
        new_pix = np.zeros_like(ink_pix)
        new_pix[:, 0] = h_new
        new_pix[:, 1] = s_new
        new_pix[:, 2] = v_new
        new_pix_u8 = np.clip(new_pix, 0, 255).astype(np.uint8)
        new_bgr = cv2.cvtColor(new_pix_u8.reshape(-1, 1, 3), cv2.COLOR_HSV2BGR).reshape(-1, 3)
        output_bgr[ink_mask] = new_bgr

        # 备用方案：染色部分红色调淡（alpha 64-127 的像素降低 alpha 和饱和度）
        if fade_light:
            light_mask = (full_alpha >= 64) & (full_alpha < 200)
            if light_mask.sum() > 0:
                # 降低淡色像素的 alpha 到 50
                full_alpha[light_mask] = np.clip(full_alpha[light_mask].astype(np.int16) - 60, 0, 255).astype(np.uint8)
                # 降低淡色像素的饱和度
                light_hsv = full_hsv[light_mask].astype(np.float32)
                light_hsv[:, 1] = np.clip(light_hsv[:, 1] * 0.4, 0, 255)  # 饱和度降为 40%
                light_u8 = np.clip(light_hsv, 0, 255).astype(np.uint8)
                light_bgr = cv2.cvtColor(light_u8.reshape(-1, 1, 3), cv2.COLOR_HSV2BGR).reshape(-1, 3)
                output_bgr[light_mask] = light_bgr

    # 输出
    output_rgb = cv2.cvtColor(output_bgr, cv2.COLOR_BGR2RGB)
    rgba = np.dstack([output_rgb, full_alpha])
    Image.fromarray(rgba, "RGBA").save(dst_path, "PNG")

    # 统计
    total = H * W
    transparent = int((full_alpha == 0).sum())
    opaque = int((full_alpha >= 200).sum())
    light = int(((full_alpha >= 64) & (full_alpha < 200)).sum())
    print(f"  {os.path.basename(dst_path)}: transparent={transparent/total*100:.1f}% opaque={opaque/total*100:.1f}% light={light/total*100:.1f}%")
    return dst_path


def make_comparison():
    """生成三版并排对比图（米黄背景）"""
    bg_color = (245, 230, 200)  # #f5e6c8
    versions = [
        ('v_current', '当前版本 (距离30, R-G下限3)'),
        ('v_improved', '改进版 (距离15, R-G下限5)'),
        ('v_faded', '备用版 (染色调淡)'),
    ]

    # 读取三个 PNG，裁剪到非透明区域
    imgs = []
    for name, label in versions:
        path = os.path.join(OUT_DIR, f'{name}.png')
        img = cv2.imread(path, cv2.IMREAD_UNCHANGED)
        if img is None:
            print(f"  {name}.png not found!")
            return
        alpha = img[:, :, 3]
        ys, xs = np.where(alpha >= 10)
        if len(ys) == 0:
            imgs.append(np.zeros((100, 100, 3), dtype=np.uint8))
            continue
        x0, x1 = xs.min(), xs.max()
        y0, y1 = ys.min(), ys.max()
        pad = 30
        x0 = max(0, x0 - pad); y0 = max(0, y0 - pad)
        x1 = min(img.shape[1], x1 + pad); y1 = min(img.shape[0], y1 + pad)
        crop = img[y0:y1, x0:x1]
        # 合成到米黄背景
        bg = np.full((crop.shape[0], crop.shape[1], 3), bg_color, dtype=np.uint8)
        a = crop[:, :, 3:4].astype(np.float32) / 255.0
        composite = (crop[:, :, :3].astype(np.float32) * a + bg.astype(np.float32) * (1 - a)).astype(np.uint8)
        imgs.append(composite)

    # 统一高度
    target_h = 600
    resized = []
    for im in imgs:
        h, w = im.shape[:2]
        scale = target_h / h
        new_w = int(w * scale)
        resized.append(cv2.resize(im, (new_w, target_h)))

    # 横向拼接，中间加分隔线
    gap = 20
    total_w = sum(im.shape[1] for im in resized) + gap * (len(resized) - 1)
    canvas = np.full((target_h + 40, total_w, 3), bg_color, dtype=np.uint8)
    x_offset = 0
    labels = [v[1] for v in versions]
    for i, im in enumerate(resized):
        canvas[:target_h, x_offset:x_offset + im.shape[1]] = im
        # 加标签
        cv2.putText(canvas, labels[i], (x_offset + 5, target_h + 25),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.5, (100, 80, 60), 1, cv2.LINE_AA)
        x_offset += im.shape[1] + gap

    comp_path = os.path.join(OUT_DIR, 'comparison.png')
    cv2.imwrite(comp_path, canvas)
    print(f"\n对比图已保存: {comp_path}")
    return comp_path


if __name__ == '__main__':
    print("生成 v_current (当前版本)...")
    run_segment(SRC, os.path.join(OUT_DIR, 'v_current.png'),
                dist_threshold=30, rg_light_lower=3, fade_light=False)

    print("\n生成 v_improved (改进版: 更激进去除纸张)...")
    run_segment(SRC, os.path.join(OUT_DIR, 'v_improved.png'),
                dist_threshold=15, rg_light_lower=5, fade_light=False)

    print("\n生成 v_faded (备用版: 染色调淡)...")
    run_segment(SRC, os.path.join(OUT_DIR, 'v_faded.png'),
                dist_threshold=30, rg_light_lower=3, fade_light=True)

    print("\n生成对比图...")
    make_comparison()
