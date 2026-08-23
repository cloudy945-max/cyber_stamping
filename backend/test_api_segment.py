"""测试 segment-test API：登录→上传 8181 + bbox→保存返回的 PNG。"""
import json
from pathlib import Path

import requests

BASE = "http://127.0.0.1:8000"
HEIC = Path(r"d:\projects\cyber_stamping\IMG_8181.HEIC")
OUT = Path(r"d:\projects\cyber_stamping\backend\test_output\api_test")
OUT.mkdir(parents=True, exist_ok=True)

# 1. 登录
print("1. 登录...")
r = requests.post(
    f"{BASE}/api/auth/login",
    data={"username": "admin", "password": "admin123"},
)
token = r.json()["access_token"]
headers = {"Authorization": f"Bearer {token}"}
print(f"   token: {token[:20]}...")

# 2. 无 bbox 测试
print("\n2. 无 bbox 全图分割...")
with open(HEIC, "rb") as f:
    r = requests.post(
        f"{BASE}/api/segment-test",
        headers=headers,
        files={"file": ("8181.heic", f, "image/heic")},
        data={"color": "red"},
    )
print(f"   status: {r.status_code}, content-type: {r.headers.get('content-type')}")
if r.status_code == 200:
    out = OUT / "api_no_bbox.png"
    out.write_bytes(r.content)
    print(f"   保存: {out} ({len(r.content)} bytes)")
else:
    print(f"   错误: {r.text[:200]}")

# 3. 带 bbox 测试
print("\n3. 带 bbox 框选分割...")
bbox = (600, 1200, 2100, 2500)  # x0,y0,x1,y1
with open(HEIC, "rb") as f:
    r = requests.post(
        f"{BASE}/api/segment-test",
        headers=headers,
        files={"file": ("8181.heic", f, "image/heic")},
        data={
            "color": "red",
            "bbox_x0": str(bbox[0]),
            "bbox_y0": str(bbox[1]),
            "bbox_x1": str(bbox[2]),
            "bbox_y1": str(bbox[3]),
        },
    )
print(f"   status: {r.status_code}, content-type: {r.headers.get('content-type')}")
if r.status_code == 200:
    out = OUT / "api_with_bbox.png"
    out.write_bytes(r.content)
    print(f"   保存: {out} ({len(r.content)} bytes)")
else:
    print(f"   错误: {r.text[:200]}")

print("\n完成")
