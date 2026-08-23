"""端到端测试：使用正式 stamp_segment 函数处理 8181.jpg"""
import sys
sys.path.insert(0, '.')

from pathlib import Path
from app.services.stamp_segment import segment_stamp
import cv2
import numpy as np

src = Path(r'test_output/module_test/8181.jpg')
dst = Path(r'test_output/module_test/8181_segmented.png')

result = segment_stamp(src, dst)

if result:
    print(f"成功: {result}")
    
    img = cv2.imread(str(result), cv2.IMREAD_UNCHANGED)
    h, w = img.shape[:2]
    print(f"输出: {w}x{h}, 通道数: {img.shape[2]}")
    
    alpha = img[:, :, 3]
    
    # 统计
    print(f"\nAlpha 统计:")
    print(f"  min={alpha.min()}, max={alpha.max()}")
    print(f"  alpha=0: {(alpha==0).sum()}/{h*w} ({(alpha==0).sum()/(h*w)*100:.1f}%)")
    print(f"  alpha<32: {(alpha<32).sum()}/{h*w} ({(alpha<32).sum()/(h*w)*100:.1f}%)")
    print(f"  alpha>=128: {(alpha>=128).sum()}/{h*w} ({(alpha>=128).sum()/(h*w)*100:.1f}%)")
    print(f"  alpha>=200: {(alpha>=200).sum()}/{h*w} ({(alpha>=200).sum()/(h*w)*100:.1f}%)")
    
    # 8 方向边框检查
    non_transparent = alpha > 0
    ys, xs = np.where(non_transparent)
    if len(xs) > 0:
        cx, cy = int(np.mean(xs)), int(np.mean(ys))
        print(f"\n非透明区域中心: ({cx}, {cy})")
        
        # 找半径
        dists = np.sqrt((xs - cx)**2 + (ys - cy)**2)
        max_r = int(dists.max())
        print(f"最大半径: {max_r}")
        
        print(f"\n8 方向边框检查 (沿 0.88r-0.98r 扫描):")
        for ang in [0, 45, 90, 135, 180, 225, 270, 315]:
            a = np.radians(ang)
            c = 0; t = 0
            for d in range(int(max_r*0.88), int(max_r*0.98), 2):
                px = int(cx + d*np.cos(a))
                py = int(cy + d*np.sin(a))
                if 0<=px<w and 0<=py<h:
                    t += 1
                    if alpha[py, px] > 32: c += 1
            rate = c/t*100 if t else 0
            status = "✅" if rate >= 95 else "❌"
            print(f"  {ang:3d}°: {rate:.0f}% {status}")
    else:
        print("全透明！")
else:
    print("失败：segment_stamp 返回 None")
