# 电子集章本（cyber_stamping）

> 个人使用的 PWA 网页应用，电子化记录走访景点 / 博物馆 / 咖啡馆等地的实体印章打卡。

## V1 版本说明

V1 是项目的第一个可用版本，实现了核心的印章上传、自动分割、多视图浏览和统计功能。完整设计方案见 [DESIGN.md](DESIGN.md)。

## 功能特性

### 已实现（V1）

- **单密码登录**：JWT 认证，保护个人数据
- **印章上传**：支持 JPG/PNG/HEIC 格式，自动提取 EXIF（日期 + GPS）
- **自动地理编码**：高德 API 反向地理编码，GPS 坐标 → 城市/地区/地址
- **印章分割算法**：智能识别印章区域，自动去除背景，颜色校正（蓝紫 → 红色），透明背景 PNG 输出
- **印章增强**：CLAHE 自适应直方图均衡 + 形态学去阴影
- **时间线视图**：按盖章日期倒序浏览，日期分组 sticky header
- **地图视图**：Leaflet + 高德/ArcGIS 瓦片图，国内外自动切换，印章位置标记
- **集章册视图**：牛皮纸背景 + 贴纸渲染 + 微旋转，模拟实体集章册质感
- **统计看板**：ECharts 总章数 / 城市数 / 月份折线 / 类型饼图 / 地区柱状
- **分割测试页面**：独立调试工具，支持框选区域 + 颜色选择 + 实时预览

### 与 DESIGN.md 的差异

| 模块 | 设计文档 | V1 实际状态 |
|---|---|---|
| 印章分割 | rembg 直接抠图 | ✅ 超越设计：rembg + R-G 软 alpha + HSV 颜色校正 + 智能边界约束 |
| 套章系列 | series 表 + SeriesView | ❌ 未实现 |
| 手动排版 | AlbumEditorView + album_pages 表 | ❌ 未实现 |
| 地区分册 | RegionalAlbumView | ❌ 未实现 |
| 印章详情 | StampDetailView | ❌ 未实现 |
| 导出备份 | export API | ❌ 未实现 |
| 重新处理 | POST /reprocess | ✅ 已实现 |
| EXIF 预览 | POST /preview-exif | ⚠️ 前端调用但后端未实现 |
| PWA 离线 | vite-plugin-pwa | ❌ 未实现 |
| 数据库迁移 | Alembic | ❌ 未引入（SQLite 自动建表） |
| 部署脚本 | deploy/ 目录 | ❌ 未实现 |
| PaperBackground 组件 | 牛皮纸纹理容器 | ⚠️ 样式内联在各视图中 |
| StampCard 组件 | 单枚印章卡片 | ⚠️ 逻辑内联在 StampSticker 中 |
| MapMarker 组件 | 地图标记 | ⚠️ 逻辑内联在 MapView 中 |

## 技术栈

| 层 | 技术 |
|---|---|
| 后端框架 | FastAPI + Uvicorn |
| ORM | SQLAlchemy 2.0 |
| 数据库 | SQLite |
| 认证 | JWT (python-jose) + passlib (bcrypt) |
| 图像处理 | OpenCV + Pillow + rembg (u2netp) |
| 地理编码 | 高德 Web 服务 API |
| 前端框架 | Vue 3 + Vite + TypeScript |
| 状态管理 | Pinia |
| 地图 | Leaflet + 高德/ArcGIS 瓦片 |
| 图表 | ECharts |
| UI | 自写组件，复古手账风

## 项目结构

```
cyber_stamping/
├── backend/
│   ├── app/
│   │   ├── main.py                 # FastAPI 入口
│   │   ├── config.py               # 环境配置
│   │   ├── database.py             # SQLite engine
│   │   ├── deps.py                 # 依赖注入
│   │   ├── security.py             # JWT 工具
│   │   ├── api/
│   │   │   ├── auth.py             # 登录认证
│   │   │   ├── stamps.py           # 印章 CRUD + 图片处理
│   │   │   ├── views.py            # 浏览聚合接口
│   │   │   ├── stats.py            # 统计接口
│   │   │   └── segment_test.py     # 分割测试 API
│   │   ├── models/
│   │   │   ├── user.py
│   │   │   ├── stamp.py
│   │   │   └── geocode_cache.py    # 地理编码缓存表
│   │   ├── schemas/
│   │   │   ├── auth.py
│   │   │   └── stamp.py
│   │   └── services/
│   │       ├── exif.py              # EXIF 提取
│   │       ├── geocode.py           # 高德逆地理编码
│   │       ├── enhance.py           # CLAHE 增强
│   │       ├── background_removal.py# rembg session 管理
│   │       ├── stamp_segment.py     # 印章分割核心算法
│   │       └── pipeline.py          # 处理管线编排
│   └── requirements.txt
├── frontend/
│   ├── src/
│   │   ├── main.ts
│   │   ├── App.vue
│   │   ├── router/index.ts
│   │   ├── stores/auth.ts
│   │   ├── api/http.ts
│   │   ├── types/
│   │   │   ├── stamp.ts
│   │   │   └── stats.ts
│   │   ├── utils/image.ts
│   │   ├── views/
│   │   │   ├── LoginView.vue
│   │   │   ├── TimelineView.vue
│   │   │   ├── MapView.vue
│   │   │   ├── StampAlbumView.vue
│   │   │   ├── UploadView.vue
│   │   │   ├── StatsView.vue
│   │   │   └── StampSegmentTest.vue
│   │   └── components/
│   │       ├── StampSticker.vue
│   │       └── StatsChart.vue
│   ├── vite.config.ts
│   └── package.json
├── data/                            # gitignore（运行时生成）
│   ├── stamps/
│   │   ├── original/
│   │   └── sticker/
│   └── cyber_stamping.db
├── DESIGN.md
├── .env.example
└── .gitignore
```

## 快速开始

### 环境要求

- Python 3.11+
- Node.js 18+
- 高德 API Key（免费申请）

### 后端

```bash
cd backend
python -m venv .venv
.venv\Scripts\activate          # Windows
# source .venv/bin/activate     # Linux/Mac
pip install -r requirements.txt

# 配置环境变量
cp ../.env.example ../.env
# 编辑 .env：设置 ADMIN_PASSWORD、AMAP_API_KEY、JWT_SECRET

# 首次运行需下载 rembg 模型（约 4.7MB）
# 模型会自动下载到 ~/.u2net/u2netp.onnx
# 或手动下载：https://github.com/danielgatis/rembg/releases/download/v0.0.0/u2netp.onnx

uvicorn app.main:app --host 127.0.0.1 --port 8000 --reload
```

### 前端

```bash
cd frontend
npm install
npm run dev
# 打开 http://localhost:5173
```

### 首次使用

1. 打开 `http://localhost:5173`，使用 `.env` 中设置的密码登录
2. 进入「上传」页面，选择印章照片
3. 系统自动提取 EXIF、地理编码、增强、分割
4. 在时间线 / 地图 / 集章册 / 统计中浏览

## 印章分割算法

V1 的印章分割超越了 DESIGN.md 中的 rembg 直接抠图方案，采用多阶段处理：

```
原图
  │
  ├─ 1. HoughCircle 圆形检测 + 轮廓筛选 → 定位印章中心与半径
  │
  ├─ 2. R-G 通道差值 → 软 alpha 计算（墨迹浓度连续映射）
  │
  ├─ 3. 智能边界约束 → 圆形搜索区域 + 最大连通域，排除非印章元素
  │
  ├─ 4. 三级 alpha 分层 → 强墨水(255) / 中墨水(200) / 淡墨水(120)
  │
  ├─ 5. HSV 颜色校正 → 蓝紫色墨水 → 红色 (H=172, S=130)
  │
  ├─ 6. 淡色调淡 → 纸张染色区域 alpha 降 60 + 饱和度降 40%
  │
  └─ 7. 输出透明背景 PNG (RGBA)
```

### 分割测试页面

访问 `/segment-test` 可独立调试分割参数：
- 上传图片 + 框选区域
- 颜色选择（自动检测 / 红色 / 蓝色 / 黑色）
- 实时预览分割结果

## 环境变量

| 变量 | 说明 | 默认值 |
|---|---|---|
| `ADMIN_PASSWORD` | 登录密码 | - |
| `JWT_SECRET` | JWT 签名密钥 | - |
| `AMAP_API_KEY` | 高德 Web 服务 API Key | - |
| `REMBG_MODEL` | rembg 模型名 | `u2netp` |
| `DATA_DIR` | 数据目录 | `data` |

## 开发路线图

| 阶段 | 状态 | 内容 |
|---|---|---|
| P1 骨架打通 | ✅ 完成 | 后端骨架 + 登录 + 印章 CRUD + 时间线 |
| P2 图片处理 | ✅ 完成 | EXIF + 地理编码 + 增强 + 分割 + 集章册 |
| P3 浏览体验 | ⚠️ 部分完成 | 地图 ✅ / 统计 ✅ / 地区分册 ❌ / 搜索筛选 ❌ |
| P4 统计与套章 | ⚠️ 部分完成 | 统计 ✅ / 套章 ❌ |
| P5 高级排版 | ❌ 未开始 | 手动排版 + 页面导出 + 备份 |
| P6 PWA 与打磨 | ❌ 未开始 | PWA 离线 + 视觉打磨 |
