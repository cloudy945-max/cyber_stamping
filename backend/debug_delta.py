"""直接在 e2e 后输出，检查 HSV 偏移"""
import sys
sys.path.insert(0, '.')

from pathlib import Path
import cv2
import numpy as np

img_bgr = cv2.imread(r'test_output/module_test/8181.jpg')
out = cv2.imread(r'test_output/module_test/8181_segmented.png', cv2.IMREAD_UNCHANGED)
full_alpha = out[:,:,3]

# 模拟颜色校正过程
output_bgr = img_bgr.copy()
ink_mask_full = full_alpha >= 32
strong_mask_full = full_alpha >= 128

print(f"墨水总数 ink_mask: {ink_mask_full.sum()}")
print(f"强墨水 strong_mask: {strong_mask_full.sum()}")

if ink_mask_full.sum() > 0 and strong_mask_full.sum() > 0:
    full_hsv = cv2.cvtColor(output_bgr, cv2.COLOR_BGR2HSV)
    ink_pix = full_hsv[ink_mask_full].astype(np.float32)
    
    # 计算强墨水 H 均值
    strong_pixels = full_hsv[strong_mask_full]
    strong_h_mean = strong_pixels[:, 0].astype(np.float32).mean()
    print(f"强墨水 H 均值(strong_h_mean): {strong_h_mean:.2f}")
    
    h_target_mean = 172.0
    delta_h = h_target_mean - strong_h_mean
    print(f"delta_h = {h_target_mean} - {strong_h_mean} = {delta_h:.2f}")
    
    h_orig = ink_pix[:, 0]
    print(f"ink_mask 中原始 H 均值: {h_orig.mean():.2f}")
    
    h_new = h_orig + delta_h
    print(f"h_new (偏移后) 均值: {h_new.mean():.2f}")
    print(f"h_new range: {h_new.min():.2f} ~ {h_new.max():.2f}")
    
    # 循环处理
    h_new = np.where(h_new > 179, h_new - 180, h_new)
    h_new = np.where(h_new < 0, h_new + 180, h_new)
    print(f"h_new (mod后) 均值: {h_new.mean():.2f}")
    print(f"h_new range: {h_new.min():.2f} ~ {h_new.max():.2f}")
    
    # 现在来看看 ink_pix 中有多少百分比的像素是 strong_mask（>=128）
    # 因为直接 full_hsv[ink_mask_full] 取出来是混合的
    # 我需要分别查看 ink_mask_strong_only, ink_mask_marginal
    
    # ink_mask_full 由两部分组成：
    only_strong = full_alpha >= 128
    marginal = (full_alpha >= 32) & (full_alpha < 128)
    
    print(f"\n强墨水(>128): {only_strong.sum()}")
    print(f"边缘墨水(32-128): {marginal.sum()}")
    
    # 重新计算：分开偏移，看各自的结果
    for label, mask in [("强墨水", only_strong), ("边缘墨水", marginal)]:
        if mask.sum() == 0: continue
        pix_h = full_hsv[mask][:, 0].astype(np.float32)
        nh = pix_h + delta_h
        nh = np.where(nh > 179, nh - 180, nh)
        nh = np.where(nh < 0, nh + 180, nh)
        print(f"\n{label} H: orig_mean={pix_h.mean():.1f} → new_mean={nh.mean():.1f}, delta={delta_h:.1f}")
    
    # 如果边缘墨水 H 差异大，就会导致 ink_mask 的混合均值偏离 172
    # 让我检查一下 strong_mask 的 h 是否真的到 172
    
    # 直接用强墨水单独做颜色校正，然后用验证方式看 HSV H
    print(f"\n\n--- 只对强墨水应用校正，检查 HSV ---")
    test_bgr = img_bgr.copy()
    mask = only_strong
    pix = full_hsv[mask].astype(np.float32)
    h_new_only = pix[:,0] + delta_h
    h_new_only = np.where(h_new_only > 179, h_new_only - 180, h_new_only)
    h_new_only = np.where(h_new_only < 0, h_new_only + 180, h_new_only)
    
    s_only = np.clip(pix[:,1]*1.8 + 40, 60, 255)
    v_only = pix[:,2]
    
    only_new = np.stack([h_new_only, s_only, v_only], axis=1).reshape(-1,1,3)
    only_new_u8 = np.clip(only_new, 0, 255).astype(np.uint8)
    only_new_bgr = cv2.cvtColor(only_new_u8, cv2.COLOR_HSV2BGR).reshape(-1,3)
    test_bgr[mask] = only_new_bgr
    
    test_hsv = cv2.cvtColor(test_bgr, cv2.COLOR_BGR2HSV)
    final = test_hsv[mask]
    print(f"  强墨水最终 H: {final[:,0].mean():.1f}")
    print(f"  强墨水最终 S: {final[:,1].mean():.1f}")
    print(f"  强墨水最终 V: {final[:,2].mean():.1f}")
