"""
stamp_extractor.config
======================
默认参数。原则：默认偏向「宁可保留淡墨，也不要误删真实图案」。
所有调参都走这里，方便统一管理。
"""
from dataclasses import dataclass, field
from typing import Tuple


# 颜色空间加权：默认更偏 chroma(a,b)，因为纸张阴影主要影响 L
@dataclass
class ExtractorConfig:
    # =============================================
    # Alpha 核心阈值（原则 13：淡墨保留）
    # =============================================
    # Lab ΔE 平滑映射的两端。
    #   ΔE < ink_low  → 认为是纸张 → Alpha 0
    #   ΔE > ink_high → 认为是墨迹 → Alpha 满值
    #   中间区域线性 smoothstep 过渡（连续，非二值）
    ink_low: float = 2.5          # 越低越会把接近纸的淡墨也保留
    ink_high: float = 12.0        # 越高越只保留强墨迹；下调=更激进保留淡墨
    alpha_strength: float = 1.10  # 对计算出的 0..1 alpha 再乘一个系数（>1 会在淡墨区更不透明）
    alpha_clamp_max: int = 255    # Alpha 上限（原则上 255）

    # =============================================
    # 纸张背景建模
    # =============================================
    # 全局纸张估计时，从图像的 L 通道里找「占比最大的高亮峰值区间」作为纸候选。
    paper_percentile_lo: float = 65.0   # L 百分位下限（低于认为不是纸）
    paper_percentile_hi: float = 97.0   # L 百分位上限（高于常是过曝/反光，但也是纸）
    # 认为是「纸候选像素」的最大 chroma = sqrt(a²+b²) 阈值
    paper_max_chroma: float = 10.0
    # 局部亮度估计高斯核半径（相对图片尺寸），用于归一化阴影（原则 11）
    local_bg_sigma_ratio: float = 0.05  # 5% 图片宽
    local_bg_enabled: bool = True
    # 局部亮度归一化强度 0..1：1 = 完全补偿阴影，0 = 不补偿
    local_bg_gain: float = 0.70

    # =============================================
    # 颜色距离组成
    # =============================================
    weight_L: float = 1.0
    weight_a: float = 2.2
    weight_b: float = 2.2
    # 额外的「饱和度加分」：如果像素 a/b 方向显著偏离纸色，再加权
    saturation_boost: float = 0.50      # 0 = 关闭
    # 「比纸更暗」的加分（专门照顾纯黑/深灰墨迹，其 chroma 不高）
    darkness_boost: float = 0.60

    # =============================================
    # 局部对比度（原则 13：细线/小字淡墨保留）
    # =============================================
    local_contrast_enabled: bool = True
    local_contrast_ksize: int = 9       # 像素，奇数
    local_contrast_strength: float = 0.30  # 0..0.5，不要过高以免放大噪点

    # =============================================
    # 噪声抑制（默认极弱/近乎关闭 — 原则 6、16）
    # =============================================
    noise_min_area: int = 0     # 像素连通域最小面积；0 = 不启用。推荐 0 或 2
    noise_median_ksize: int = 0 # 中值滤波核；0 = 不启用。推荐 0 或 3
    # 注意：坚决不使用 MORPH_CLOSE / FillHoles / 膨胀腐蚀大核

    # =============================================
    # 输出控制
    # =============================================
    auto_crop: bool = True
    auto_crop_alpha_threshold: int = 12  # Alpha > 该值才计为「真实墨迹」
    auto_crop_border: int = 2            # bbox 外扩像素，防切边
    save_debug_images: bool = True
    # 是否启用「纸张染色去除」实验模式（默认关闭 — 原则 8）
    desaturate_paper_tint: bool = False

    # =============================================
    # 邮票/截图「外围区域强制清零」开关（新增，针对 img1~3 jfif 聊天截图）
    #
    # 目标：把「邮票齿孔之外的聊天白背景 / 截图杂边」全部强制 alpha=0 删除。
    # 注意：只删 region 外面。region 内部的纸张空白仍然通过 InkScore 透明化，
    #       绝不会把整个矩形/圆形邮票内部当成实体填实（符合原则 3、测试 A）。
    # =============================================
    drop_outer_stamp_region: bool = True
    # 判定「聊天背景纯白」的阈值（真实 Lab 空间）
    chat_bg_L_min: float = 96.0          # L ≥ 该值且 chroma ≤ chat_bg_chroma_max → 聊天背景
    chat_bg_chroma_max: float = 4.0
    # region mask 的齿孔闭合（轻微！仅用于把邮票齿牙连成一体）。
    # 这是唯一允许的 morphological 操作，并且只作用于 region 判定，
    # 绝对不作用于 Alpha 墨迹本身（严格遵守原则 6）。
    stamp_region_close_px: int = 3       # 圆盘核半径
    stamp_region_border_px: int = 4      # 找到 region 后外扩几像素，防误切邮票最外齿牙

    # 方法二：基于「已算好的 Alpha 墨水分布」直接推导邮票外轮廓多边形。
    # 更可靠，因为它直接根据墨水在哪里决定"邮票本体大致长什么样"。
    # 对于"方形工作图中有个圆形邮票"的情况（如 img1~2），会把四角白纸强行清零。
    # 同样：只删 polygon 外面，不会填实内部（严格遵守原则 3、6、测试 A/B）。
    drop_outside_stamp_outline: bool = True
    outline_close_bridge_px: int = 32    # 桥接环形外轮廓缺口的 closing 半径（越大越能跨越大缺口）
    outline_outer_border_px: int = 10    # polygon 外扩安全边（用于包含最外圈齿孔/齿牙）
    outline_seed_alpha_thr: int = 60     # 作为轮廓种子的最小墨水 Alpha（默认 60；排除纸纹理/压缩伪影杂点）
    outline_ignore_border_px: int = 0   # 忽略工作图最外圈多少种子（subregion 模式建议 40，防止裁切边的杂点被 closing 撑到整图；0 = 自适应：自动 = close_bridge_px + 8）
    outline_seed_chroma_min: float = 8.0  # 种子最小 chroma（sqrt(a²+b²)）；排除"高 alpha 低饱和"的灰色背景被误当墨水种子

    # =============================================
    # 近纯黑「聊天截图 letterbox / 黑边 / 黑框」硬清零
    # =============================================
    # 典型场景：jfif 聊天截图的方形工作图最外圈有一圈纯黑 RGB(0,0,0) 或近纯黑的
    # letterbox 黑边，它离纸色极远 → InkScore 把它当作"最浓的墨水" → alpha=255。
    # 但真实印章/邮票印在纸上的墨迹，绝不会变成「R,G,B 全部 < 10」的纯死黑（总有点
    # 纸色漫反射 / JPG 压缩杂色）。所以我们把这种近纯黑像素直接判为截图 artifact，
    # 在「Alpha 生成后、outline mask 计算之前」强制清零，既解决外围黑边残留，也
    # 让 outline mask 能正确推导邮票本身的外形。
    artifact_pure_black_max_rgb: int = 15   # R,G,B 全都 ≤ 该值 → 判为近纯黑 artifact
    artifact_pure_black_drop: bool = True   # 近纯黑像素强制 alpha=0（原则 6：只删，不改动 RGB）

    @staticmethod
    def defaults() -> "ExtractorConfig":
        return ExtractorConfig()

    # 快速预设：更保守（干净）/ 更激进（保淡墨）
    @staticmethod
    def conservative() -> "ExtractorConfig":
        c = ExtractorConfig.defaults()
        c.ink_low = 3.5
        c.ink_high = 14.0
        c.alpha_strength = 1.0
        c.noise_min_area = 2
        c.local_contrast_strength = 0.15
        return c

    @staticmethod
    def preserve_light_ink() -> "ExtractorConfig":
        c = ExtractorConfig.defaults()
        c.ink_low = 1.5
        c.ink_high = 9.0
        c.alpha_strength = 1.20
        c.noise_min_area = 0
        c.local_contrast_strength = 0.45
        return c
