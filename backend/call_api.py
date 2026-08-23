"""用 requests 调用后端 API 测试正式效果"""
import sys, types, json
from pathlib import Path
import cv2
import numpy as np

src = Path(r"test_output/module_test/8181.jpg")
img = cv2.imread(str(src))
h, w = img.shape[:2]
r_roi = int(min(w, h) * 0.25)
cx_img, cy_img = w // 2, int(h * 0.55)
bbox = [cx_img - r_roi, cy_img - r_roi, cx_img + r_roi, cy_img + r_roi]

import urllib.request
url = "http://127.0.0.1:8000/api/testing/segment-test"
data = json.dumps({"image_path": str(src).replace("\\","/"), "bbox": bbox, "color": "auto"}).encode()
req = urllib.request.Request(url, data=data, headers={"Content-Type": "application/json"})
try:
    resp = urllib.request.urlopen(req, timeout=180)
    result = json.loads(resp.read())
    print(json.dumps(result, ensure_ascii=False, indent=2))
except Exception as e:
    print(f"API 调用失败: {e}")
    import traceback; traceback.print_exc()
