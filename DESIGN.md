# 电子集章本（cyber_stamping）· 方案设计

> 个人使用的 PWA 网页应用，电子化记录走访景点 / 博物馆 / 咖啡馆等地的实体印章打卡，兼容部分纯照片打卡。

---

## 系统架构总览

```
┌─────────────────────────────────┐
│         PWA 前端 (Vue 3)          │
│   4 浏览视图 + 上传排版           │
└───────────────┬─────────────────┘
                │ HTTPS · JWT
┌───────────────▼─────────────────┐
│      FastAPI 后端 · Python        │
│  ┌────────────┐  ┌────────────┐ │
│  │ API 路由层  │  │ 图片处理管线 │ │ ◀ 焦点
│  └────────────┘  └────────────┘ │
└──┬─────────────┬───────────┬────┘
   │ SQLAlchemy   │ 文件读写   │ 地理编码
┌──▼─────────┐ ┌──▼────────┐  ┌──▼──────────┐
│ SQLite 数据库│ │图片文件存储│  │ 高德地图 API  │ (外部)
└────────────┘ └───────────┘  └─────────────┘

部署：云服务器 · Nginx 反代 · HTTPS · 单密码登录保护
```

---

## 一、技术栈选型

| 层 | 选型 | 备选 | 理由 |
|---|---|---|---|
| 后端框架 | **FastAPI** | Flask | 类型提示充分、自动 OpenAPI 文档、异步友好 |
| ASGI 服务器 | Uvicorn + systemd | Gunicorn+uvicorn worker | 单机个人项目，无需多进程管理复杂度 |
| ORM | **SQLAlchemy 2.0** | SQLModel | 成熟稳定、类型提示完善 |
| 数据库迁移 | Alembic | 手写 SQL | 版本化管理 schema 变更 |
| 数据库 | SQLite | PostgreSQL | 个人项目无并发压力，零部署、单文件易备份 |
| 认证 | JWT（python-jose）+ passlib(bcrypt) | Session | 无状态、PWA 友好；单密码登录场景足够 |
| EXIF 提取 | Pillow (PIL.Image.Exif) | exifread | Pillow 已是图片处理基础依赖 |
| 印章增强 | Pillow + OpenCV | 全 Pillow | OpenCV 自适应阈值/形态学操作对印章去阴影更强 |
| 抠图去背景 | **rembg**（u2net 模型） | OpenCV 传统分水岭 | rembg AI 抠图质量高、API 极简；体积大但可接受 |
| 反向地理编码 | **高德 Web 服务 API** | Nominatim/腾讯位置服务 | 国内精度高、免费额度（个人每日 5000 次）充足 |
| 前端框架 | **Vue 3 + Vite + TypeScript** | React | Python 背景下 Vue 模板语法更直观；TS 类型安全 |
| PWA | vite-plugin-pwa | 手写 manifest | 一键生成 service worker + manifest，离线+可安装 |
| 状态管理 | Pinia | Vuex | Vue 3 官方推荐，TS 友好 |
| 地图组件 | Leaflet + 高德瓦片图 | 高德 JS API | Leaflet 开源轻量、不绑定商业 SDK |
| 图表 | ECharts（按需引入） | Chart.js | 统计看板需要丰富图表类型，中文生态好 |
| 拖拽排版 | vue-draggable-plus + interact.js | sortablejs | 印章自由拖拽+旋转缩放用 interact.js，网格排序用 draggable |
| UI 组件 | 自写组件 + 少量基础组件 | Element Plus | 复古手账风高度定制，重型组件库反而干扰视觉 |
| 反代/HTTPS | Nginx + Let's Encrypt(certbot) | Caddy | Nginx 配置成熟；PWA 必须 HTTPS |
| 进程守护 | systemd | supervisor | 云服务器原生支持，零额外依赖 |

---

## 二、项目目录结构

```
cyber_stamping/
├── backend/
│   ├── app/
│   │   ├── main.py                  # FastAPI 入口 + 路由挂载
│   │   ├── config.py                # Settings（pydantic-settings，环境变量）
│   │   ├── database.py              # engine + SessionLocal
│   │   ├── deps.py                  # 依赖注入（当前用户、DB session）
│   │   ├── models/                  # SQLAlchemy ORM
│   │   │   ├── user.py
│   │   │   ├── stamp.py
│   │   │   ├── series.py
│   │   │   └── album.py             # 集章册页面 + 摆放
│   │   ├── schemas/                 # Pydantic 请求/响应模型
│   │   ├── api/
│   │   │   ├── auth.py              # 登录发 token
│   │   │   ├── stamps.py            # 印章 CRUD + 重新处理
│   │   │   ├── views.py             # 时间线/地区/地图/相册 聚合接口
│   │   │   ├── series.py
│   │   │   ├── stats.py
│   │   │   ├── album.py             # 手动排版页面
│   │   │   └── export.py            # 备份 + 页面导出
│   │   └── services/
│   │       ├── exif.py              # EXIF 提取（时间+GPS）
│   │       ├── geocode.py           # 高德逆地理编码（带本地缓存）
│   │       ├── enhance.py           # 印章增强（灰度+自适应阈值+去阴影）
│   │       ├── background_removal.py# rembg 抠图
│   │       └── pipeline.py          # 上传处理总编排
│   ├── alembic/                     # 迁移版本
│   ├── tests/
│   ├── requirements.txt
│   └── alembic.ini
├── frontend/
│   ├── src/
│   │   ├── main.ts
│   │   ├── App.vue
│   │   ├── router/index.ts
│   │   ├── stores/                  # Pinia: auth/stamps/series/stats
│   │   ├── api/                     # axios 封装 + 拦截器（JWT 注入）
│   │   ├── views/
│   │   │   ├── Login.vue
│   │   │   ├── TimelineView.vue
│   │   │   ├── RegionalAlbumView.vue
│   │   │   ├── MapView.vue
│   │   │   ├── StampAlbumView.vue   # 网格相册（手账质感）
│   │   │   ├── StampDetailView.vue
│   │   │   ├── UploadView.vue       # 上传（EXIF 预填+预览）
│   │   │   ├── SeriesView.vue
│   │   │   ├── StatsView.vue
│   │   │   └── AlbumEditorView.vue  # 手动拖拽排版
│   │   ├── components/
│   │   │   ├── StampCard.vue        # 单枚印章卡片
│   │   │   ├── StampSticker.vue     # 透明贴纸渲染（含阴影/旋转）
│   │   │   ├── PaperBackground.vue  # 牛皮纸纹理容器
│   │   │   ├── MapMarker.vue
│   │   │   └── StatsChart.vue
│   │   ├── styles/
│   │   │   ├── theme.scss           # 复古手账风变量
│   │   │   └── paper-texture.css
│   │   └── utils/exif.ts            # 前端 EXIF 预览（上传前即时反馈）
│   ├── public/manifest.webmanifest
│   ├── vite.config.ts
│   └── package.json
├── data/                            # gitignore
│   ├── stamps/
│   │   ├── original/
│   │   └── sticker/
│   └── cyber_stamping.db
├── deploy/
│   ├── nginx.conf
│   ├── cyber-stamping.service      # systemd unit
│   └── deploy.sh
├── .env.example
└── requirements.txt
```

---

## 三、数据库表设计

### stamps（印章记录主表）

| 字段 | 类型 | 说明 |
|---|---|---|
| id | INTEGER PK | |
| original_path | TEXT | 原图相对路径 |
| sticker_path | TEXT | 抠图后透明贴纸路径 |
| stamp_date | DATE | 盖章日期（EXIF 提取，可手改） |
| uploaded_at | DATETIME | 上传时间 |
| location_name | TEXT | 地点名称 |
| address | TEXT | 详细地址 |
| city | TEXT | 城市 |
| region | TEXT | 省/大区 |
| latitude | REAL | 纬度 |
| longitude | REAL | 经度 |
| type | TEXT | 类型：景点/博物馆/咖啡馆/书店/驿站/其它 |
| notes | TEXT | 感想/备注 |
| series_id | INTEGER FK→series | 所属套章（可空） |
| series_index | INTEGER | 在套章中的序号（如第 3/12） |
| is_photo_only | BOOLEAN | 是否纯照片打卡（无印章） |
| created_at / updated_at | DATETIME | |

### series（套章系列）

`id, name, description, total_count, created_at`

### album_pages（集章册页面）

`id, title, layout_mode('auto'|'manual'), background, created_at`

### page_placements（印章在页面摆放——手动排版）

`id, page_id FK, stamp_id FK, pos_x, pos_y(相对0-1), rotation, scale, z_index, created_at`

### users（单用户）

`id, username UNIQUE, password_hash, created_at`

---

## 四、核心 API 设计

```
认证
POST /api/auth/login                          密码 → JWT

印章 CRUD
GET  /api/stamps?city=&type=&date_from=&date_to=&q=&page=
GET  /api/stamps/{id}
POST /api/stamps                               multipart：图片+元数据（上传触发处理管线）
PUT  /api/stamps/{id}                          修改元数据（含手改日期/地点）
DELETE /api/stamps/{id}
POST /api/stamps/{id}/reprocess               重跑增强/抠图（调参后）
GET  /api/stamps/{id}/image?variant=original|sticker

浏览聚合
GET /api/views/timeline?cursor=               时间线游标分页
GET /api/views/regions                        [{city, count, cover_sticker}] 地区分册
GET /api/views/map/points                     [{id, lat, lng, location_name}] 地图标记
GET /api/views/album?page=&size=              网格相册

套章系列
GET/POST /api/series
GET  /api/series/{id}                          含进度：{total, collected, stamps[]}

统计
GET /api/stats/overview                       {total, cities, regions, series_count}
GET /api/stats/by-month                       月份分布
GET /api/stats/by-type                        类型分布
GET /api/stats/by-region                      地区 Top N + Other

集章册页面（手动排版）
GET/POST /api/album/pages
PUT  /api/album/pages/{id}                    更新页面元数据
GET/PUT /api/album/pages/{id}/placements      摆放列表（批量更新位置）

导出/分享
GET /api/export/backup                        全量 zip（DB + 图片）
POST /api/album/pages/{id}/export             页面导出为图片（服务端截图渲染）
```

---

## 五、图片处理管线（核心特色）

上传一张印章照片的完整流程：

```
原图上传
   │
   ▼
[1] Pillow 读 EXIF
      DateTimeOriginal → stamp_date
      GPSInfo          → lat/lng
   │
   ▼
[2] 高德逆地理编码（带本地 SQLite 缓存，避免重复调用）
      lat/lng → {country, region, city, address}
   │
   ▼
[3] 印章增强 (OpenCV)
      灰度化 → CLAHE 自适应直方图均衡
            → 自适应阈值二值化（突出印章）
            → 形态学开运算去纸张纹理/阴影
      输出 enhanced.png
   │
   ▼
[4] rembg 抠图（u2net 模型）
      输入 enhanced → 输出透明背景 sticker.png
   │
   ▼
[5] 写库：original_path / sticker_path / EXIF 元数据 / 地理信息
```

### 关键工程点

- **处理异步化**：上传接口立即返回 `stamp_id`（pending 状态），后台任务跑管线，前端轮询或 SSE 推送完成状态
- **抠图模型常驻**：rembg 首次启动加载较慢，启动时预加载到内存常驻
- **EXIF 缺失兜底**：日期默认今天、GPS 缺失则地点字段留空，由用户手填
- **重新处理接口**：调整增强参数后重跑步骤 3-4，原图不丢

---

## 六、前端模块与关键交互

### 视图划分

| 视图 | 核心组件 | 要点 |
|---|---|---|
| 时间线流 | TimelineView | 按盖章日期倒序，类朋友圈滑动；日期分组 sticky header |
| 地区分册 | RegionalAlbumView | 顶部城市 chips，点选切换；封面用该城市第一枚贴纸 |
| 地图视图 | MapView | Leaflet + 高德瓦片；聚合点（同址多章）；点 marker 弹窗预览 |
| 网格相册 | StampAlbumView | **实体集章册质感**：牛皮纸背景、装订线、贴纸+阴影+微旋转 |
| 上传 | UploadView | 选图后**前端先用 EXIF 库即时预填**预览（不等后端），用户确认后上传 |
| 手动排版 | AlbumEditorView | interact.js 拖拽+旋转+缩放；自动/手动模式切换；双指捏合（移动端） |
| 统计 | StatsView | ECharts：总章数、城市数、月份折线、类型饼图、地区柱状 |
| 套章 | SeriesView | 套章卡片网格，每张显示 x/total 进度条，缺章位置占位虚框 |

### 实体集章册质感实现要点

- 背景：CSS 重复纹理（牛皮纸 SVG noise）+ 米黄底色 `#F5E6C8`
- 主色：深棕褐 `#6B4423`，辅助浅棕 `#8B6F47`，强调印章红 `#C8403C`
- 字体：标题 Noto Serif SC（衬线复古），正文 Noto Sans SC
- 贴纸渲染：`StampSticker.vue` 组件统一加 `drop-shadow` + 随机微旋转 `±3°`，模拟盖印
- 相册网格：双线边框 + 装订孔 + 手撕毛边 mask + 手写注释字体

---

## 七、视觉风格规范

| 角色 | 色值 | 用途 |
|---|---|---|
| 背景 | `#F5E6C8`（米黄牛皮纸） | 全局底色 |
| 主色 | `#6B4423`（深棕褐） | 标题、边框、主按钮 |
| 辅助 | `#8B6F47`（浅棕） | 次级文字、分割线 |
| 强调 | `#C8403C`（印章红） | 章/标记点缀、激活态 |
| 文字 | `#3D2817`（深褐墨） | 正文 |
| 卡片 | `#FBF1DD`（浅纸） | 卡片底，比背景略亮 |

字体：标题 `Noto Serif SC`；正文 `Noto Sans SC`；手写注释可选 `Ma Shan Zheng`。

---

## 八、部署方案

- **服务器**：轻量应用服务器 2核4G（约 ¥60-80/月，rembg 模型常驻内存需 ~1.5G）
- **域名 + HTTPS**：Let's Encrypt + certbot 自动续期
- **Nginx**：托管前端静态资源 → `/api/*` 反代到 `uvicorn 127.0.0.1:8000`
- **后端**：`uvicorn app.main:app --host 127.0.0.1 --port 8000`，systemd 守护 + 失败重启
- **备份**：cron 每日打包 `data/`（DB + 图片）→ 异地对象存储（如阿里云 OSS）
- **环境变量**：`.env` 管理密码哈希盐、JWT 密钥、高德 API key、数据路径

---

## 九、开发路线图（分阶段）

| 阶段 | 内容 | 产出 |
|---|---|---|
| **P1 骨架打通** | 后端骨架+SQLite+单密码登录；印章 CRUD+原图上传；前端：登录+上传+时间线 | 能上传原图、看时间线 |
| **P2 图片处理** | EXIF+逆地理编码+印章增强+rembg 抠图；贴纸渲染组件；网格相册（手账质感） | 完整处理管线+质感相册 |
| **P3 浏览体验** | 地区分册+地图视图+搜索筛选；上传前端 EXIF 即时预填 | 四种浏览方式齐备 |
| **P4 统计与套章** | 统计看板（ECharts）+ 套章系列管理+进度跟踪 | 数据可视化+套章 |
| **P5 高级排版** | 手动拖拽排版编辑器（interact.js）+ 页面导出图片 + 全量备份 | 自由排版+导出分享 |
| **P6 PWA 与打磨** | PWA 离线+主屏安装；视觉细节打磨；性能优化 | 可安装、离线可用 |

每阶段独立可验证，P1 完成即有可用 MVP。

---

## 十、技术决策（已确认）

| 项 | 决策 |
|---|---|
| 抠图方案 | **rembg**（u2net 模型，AI 抠图，质量优先） |
| 反向地理编码 | **高德 Web 服务 API**（逆地理编码，需注册 key） |
| 地图底图 | **Leaflet + 高德瓦片图** |
| 云服务器 | **腾讯轻量应用服务器**（2核4G，部署脚本按腾讯云适配） |
