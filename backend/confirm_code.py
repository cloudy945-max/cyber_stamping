"""直接检查磁盘文件 + import 模块确认代码是否最新"""
import sys, inspect, importlib, os

# 读磁盘文件
path = r'd:\projects\cyber_stamping\backend\app\services\stamp_segment.py'
with open(path, encoding='utf-8') as f:
    disk_src = f.read()

has_color_fix = '颜色校正' in disk_src
has_bgr2rgb = 'BGR2RGB' in disk_src
print(f'磁盘文件：颜色校正={has_color_fix}, BGR2RGB={has_bgr2rgb}')

# 再 import
sys.path.insert(0, r'd:\projects\cyber_stamping\backend')
for k in list(sys.modules.keys()):
    if 'stamp' in k.lower() or 'app.services' in k:
        del sys.modules[k]
m = importlib.import_module('app.services.stamp_segment')
src = inspect.getsource(m.segment_stamp)
print(f'Import 后：颜色校正={("颜色校正" in src)}, BGR2RGB={("BGR2RGB" in src)}')
