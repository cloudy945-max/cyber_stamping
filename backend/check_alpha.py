"""检查 API 输出的 alpha 分布和墨水覆盖率"""
import cv2, numpy as np

for label, p in [('local', r'test_output/module_test/8181_segmented.png'),
                  ('API', r'test_output/api_test/api_no_bbox.png')]:
    img = cv2.imread(p, cv2.IMREAD_UNCHANGED)
    alpha = img[:,:,3]
    total = alpha.size
    transparent = (alpha == 0).sum()
    opaque = (alpha >= 200).sum()
    semi = ((alpha > 0) & (alpha < 200)).sum()
    print(f"{label}: 总{total} 透明={transparent}({transparent/total*100:.1f}%) 不透明={opaque}({opaque/total*100:.1f}%) 半透明={semi}({semi/total*100:.1f}%)")
