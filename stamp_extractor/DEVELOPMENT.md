# stamp_extractor 开发记录

## 项目目标

从纸张照片中高保真提取印章/邮戳墨迹的 Alpha 通道，输出 RGBA PNG（纸张区域透明，墨迹区域保留原始颜色与浓淡），作为 cyber_stamping 主项目的抠图引擎升级方案。

## 硬约束

1. **禁止使用云端 API、AI 大模型、图像生成或分割模型**——仅限 Python + OpenCV + Pillow + NumPy
2. **RGB 原始值不可修改**——只计算 Alpha 通道
3. **Alpha 必须为连续值**（smoothstep 映射），不可做二值化
4. **保留原始墨迹的所有缺陷**——颗粒、缺墨、断线、模糊、磨损、边缘毛刺，严禁重新绘制/修复/锐化/美化/矢量化
5. 输出为 RGBA PNG，纸张区域（外部及内部空白）全部透明
6. 印章边界识别仅基于墨迹 Alpha 值，不依赖图片边缘、白纸边缘、邮票齿孔或矩形裁剪框

## 模块结构

```
stamp_extractor/
├── __init__.py
├── config.py              # ExtractorConfig 数据类 + 3 种预设
├── processor.py           # StampExtractor 主类 + ExtractResult
├── alpha_mask.py          # score_to_alpha() 连续 Alpha 映射 + very_light_denoise()
├── background.py          # PaperModel + 纸张颜色估计 + 局部亮度归一化
├── color_analysis.py      # fused_ink_score() 多指标融合
├── edge_processing.py     # 边缘处理工具
├── utils.py               # IO、Lab 转换、子区域定位、外围 mask 计算
├── batch_processor.py     # 批量处理入口
├── app.py                 # CLI 入口（argparse）
├── checkpoint_v1_params.py  # v1 参数快照（回滚参考）
├── checkpoint_v2_params.py  # v2 参数快照（回滚参考）
└── DEVELOPMENT.md         # 本文件
```

## 算法流程

```
Input RGB
  │
  ├─ 0a. 全图 Lab → 邮票外围区域 mask（删除聊天白背景）
  │     └─ compute_stamp_paper_region_mask()
  │
  ├─ 0b. 定位印章子区域（裁掉截图/聊天框非章背景）
  │     └─ locate_stamp_subregion_bbox()
  │
  ├─ 1. RGB → Lab float32（真实感知 Lab：L∈[0,100], a/b∈[-128,127]）
  │
  ├─ 2. 局部亮度归一化（L 通道，高斯模糊补偿光照不均）
  │     └─ apply_local_luminance_correction()
  │
  ├─ 3. 全局纸张建模（从归一化后的 Lab 估计纸色）
  │     └─ estimate_paper_from_lab_float() → PaperModel
  │
  ├─ 4. 融合 InkScore（多指标加权）
  │     └─ fused_ink_score()
  │         ├─ ColorDistanceScore（Lab ΔE，weight_L/a/b 加权）
  │         ├─ SaturationScore（chroma 偏离纸色 → 加分）
  │         ├─ DarknessScore（比纸更暗 → 加分）
  │         └─ LocalContrastScore（局部对比度，保留细线/小字淡墨）
  │
  ├─ 5. 连续 Alpha 映射（smoothstep，非二值）
  │     └─ score_to_alpha()
  │
  ├─ 6. 极轻去噪（默认近乎关闭，noise_min_area=0）
  │
  ├─ 6a. 近纯黑 artifact 硬清零（聊天截图黑边 RGB≤15 → alpha=0）
  │
  ├─ 6b. 外围区域强制清零（两策略取交集）
  │     ├─ 方案A: region_mask（从 Lab 空间定位非聊天背景最大连通域）
  │     └─ 方案B: outline_mask（从 Alpha 墨水分布推导外轮廓多边形）
  │
  ├─ 7. BBox 裁剪（按真实墨迹 Alpha，不是纸边）
  │
  └─ 8. 构建 RGBA（RGB 原样 + Alpha）→ 保存 PNG
```

## 三种预设参数

| 预设 | ink_low | ink_high | alpha_strength | noise_min_area | 适用场景 |
|---|---|---|---|---|---|
| **default** | 2.5 | 12.0 | 1.10 | 0 | 大多数印章，兼顾淡墨与背景干净 |
| **preserve_light** | 1.5 | 9.0 | 1.20 | 0 | 墨迹很淡、外圈文字快看不清时 |
| **conservative** | 3.5 | 14.0 | 1.00 | 2 | 纸张很脏/背景复杂，宁丢淡墨也要干净 |

## 公开 API

```python
from stamp_extractor.processor import StampExtractor
from stamp_extractor.config import ExtractorConfig

# 初始化（使用预设）
cfg = ExtractorConfig.defaults()  # 或 .preserve_light_ink() / .conservative()
extractor = StampExtractor(cfg)

# 单图处理（文件路径输入）
result = extractor.extract_file(
    input_path=Path("input.jpg"),
    output_png=Path("output.png"),
    debug_dir=Path("debug/"),  # 可选，None 跳过调试图
)

# 单图处理（numpy 数组输入）
result = extractor.extract_array(
    rgb_uint8=rgb_array,  # (H,W,3) uint8
    output_png=Path("output.png"),
    debug_dir=None,
    source_name="test_image",
)

# 返回值 ExtractResult
result.rgba           # (H,W,4) uint8 最终 RGBA（可能已 auto_crop）
result.alpha          # (H,W) uint8 裁剪后 Alpha
result.alpha_fullres  # 未裁剪的原始分辨率 Alpha
result.bbox           # 裁剪区域 (x0,y0,x1,y1) 或 None
result.paper          # PaperModel（含 lab_mean, lab_std, n_samples）
result.stats          # Dict 统计信息
```

## CLI 用法

```bash
# 单张处理
python stamp_extractor/app.py -i input/photo.jpg -o output/

# 批量处理 + 调试图
python stamp_extractor/app.py -i input/ -o output/ --debug debug/

# 使用 preserve_light 预设
python stamp_extractor/app.py -i input/ -o output/ --preset preserve_light

# 自定义参数覆盖
python stamp_extractor/app.py -i input/ -o output/ --ink-low 1.8 --ink-high 9 --alpha-strength 1.2
```

## 开发历程

### v1 基础版（2026-08-28 ~ 08-29）

**目标**：搭建从 Lab 色彩空间到连续 Alpha 的完整管线。

**关键决策**：
- 选用 Lab 色彩空间而非 HSV——纸张阴影主要影响 L 通道，Lab 能将亮度与色度分离
- 修正 OpenCV uint8 Lab（0-255 压缩）为真实感知 Lab（L∈[0,100], a/b∈[-128,127]）
- 纸色估计必须在局部亮度归一化之后进行（同一空间），否则出现"苹果 vs 橘子"的 mismatch
- Alpha 生成使用 smoothstep 映射，确保连续过渡而非二值化
- 默认 `noise_min_area=0`——宁可保留噪点也不误删真实缺陷

**验证**：IMG_8181.HEIC 棋盘格预览确认效果，内部空白透明化正确。

### v2 外围区域清零（2026-08-29 ~ 09-04）

**问题**：3 张 jfif 聊天截图（img875963/img075266/img415767）外围残留大量非章区域。

**根因分析**：
1. 聊天截图最外圈有 80px 厚纯黑 letterbox（RGB=[0,0,0]），InkScore 将其误判为最浓墨水 → alpha=255
2. closing(r=32) 把 letterbox 和邮票内墨水连成一片，最大 contour 覆盖整图 → region_ratio=1.0
3. img415767 的灰色聊天背景因低饱和度被误判为墨水种子

**三层修复**：
1. **近纯黑 artifact 硬清零**：RGB 三通道全部 ≤15 的像素直接判为截图 artifact，alpha=0
2. **方案A - region mask**：从全图原始 Lab 出发，定位非聊天背景的最大连通域 = 邮票纸本体
3. **方案B - outline mask**：从已算好的 Alpha 墨水分布推导外轮廓多边形，删除方形图的四角白纸
4. **chroma 门槛**：`outline_seed_chroma_min=8.0`，排除高 alpha 低饱和度的灰色背景被误当墨水种子

**最终效果**：三预设 × 三图片共 9 张输出 PNG 全部为 RGBA 格式，外围透明率 >90%。

### 验证结果（2026-09-04）

| 图片 | 尺寸 | 格式 | 透明区域占比 | 平均 Alpha |
|---|---|---|---|---|
| img875963 | 1006×1006 | RGBA 8bit ✓ | ~49% | ~101 |
| img075266 | 1006×1006 | RGBA 8bit ✓ | ~49% | ~101 |
| img415767 | 1006×792 | RGBA 8bit ✓ | ~49% | ~101 |

处理时间：单图 1-2 秒。

## 踩坑记录

| 问题 | 原因 | 解决方案 |
|---|---|---|
| Alpha 全为 255 | OpenCV uint8 Lab 压缩导致色距失真 | 改用 float32 真实感知 Lab |
| 纸色估计不稳定 | 单一角落像素采样被异常值污染 | 多区域采样 + 迭代剔除离群点 + 样本保留率 ≥60% |
| 淡墨丢失 | ink_low 阈值过高 | 新增 preserve_light 预设（ink_low=1.5） |
| 聊天背景检测失败 | 仅看边框像素比例 | 改为 Lab 空间 L≥96 + chroma≤4 双条件 |
| OpenCV floodFill 报错 | 大图 floodFill 内存不足 | 替换为 drawContours 填充 |
| 灰色背景被误判为墨水 | 低饱和度但 alpha 高 | 增加 seed_chroma_min=8.0 门槛 |
| 即梦 AI 方案废弃 | i2i_v30 在生成阶段删除极暗细节，无法恢复 | 放弃 AI 图生图，回归纯 OpenCV |
| 边缘高斯模糊导致颜色变化 | σ=0.8 的 3×3 模糊改变了图章整体色调 | 当前版本不采用边缘平滑 |

## 与主程序集成方案（待实施）

现有 `backend/app/services/stamp_segment.py` 的 `segment_stamp()` 使用 R-G 通道分层 + rembg 方案，存在以下局限：
- 依赖 rembg 模型（需下载、内存占用大）
- R-G 分层仅适用于红色印章，蓝/黑印章效果差
- Alpha 为分档值（255/200/120/0），非连续过渡

集成方案：新增 `segment_stamp_v2()` 适配函数，对齐签名 `(src_path, dst_path, bbox, preset) → Optional[Path]`，通过配置开关 `segment_method` 切换。不替换现有代码，先并行测试验证。

详见主项目 `DESIGN.md`。
