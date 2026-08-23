<script setup lang="ts">
import { onMounted, onUnmounted, ref, shallowRef } from 'vue'
import { useRouter } from 'vue-router'
import L from 'leaflet'
import 'leaflet/dist/leaflet.css'
import { http } from '@/api/http'
import { useAuthStore } from '@/stores/auth'
import { stampImageUrl } from '@/utils/image'

interface MapPoint {
  id: number
  latitude: number
  longitude: number
  location_name: string | null
  type: string | null
  country: string | null
  region: string | null
  city: string | null
  address: string | null
  stamp_date: string | null
  is_photo_only: boolean
}

// 图层模式：auto=自动切换(国内高德/国外ArcGIS街道) | street=强制街道 | satellite=强制卫星
type LayerMode = 'auto' | 'street' | 'satellite'

const router = useRouter()
const auth = useAuthStore()

const mapEl = ref<HTMLDivElement | null>(null)
const map = shallowRef<L.Map | null>(null)
const loading = ref(false)
const error = ref('')
const totalCount = ref(0)
const cityFilter = ref('')
const typeFilter = ref('')

// 图层状态
const layerMode = ref<LayerMode>('auto')
const currentRegion = ref<'domestic' | 'overseas'>('domestic')

// 图层引用
const amapLayer = shallowRef<L.TileLayer | null>(null)
const arcgisStreetLayer = shallowRef<L.TileLayer | null>(null)
const arcgisImageryLayer = shallowRef<L.TileLayer | null>(null)
const activeLayer = shallowRef<L.TileLayer | null>(null)

// 印章图片 URL（含 access_token query，浏览器 <img> 自动加载）
function getImageUrl(id: number): string {
  return stampImageUrl(id, 'original')
}

// 自定义复古风 marker icon（圆形印章质感）
const stampIcon = L.divIcon({
  className: 'stamp-marker',
  html: `<div class="stamp-dot"><span>●</span></div>`,
  iconSize: [28, 28],
  iconAnchor: [14, 14],
  popupAnchor: [0, -16],
})

function popupHtml(p: MapPoint): string {
  const loc = p.location_name || '未命名地点'
  const date = p.stamp_date || '—'
  const type = p.type || ''
  const typeBadge = type ? `<span class="pp-tag">${type}</span>` : ''
  const photoBadge = p.is_photo_only ? `<span class="pp-tag muted">仅照片</span>` : ''
  // 完整地址：国家 / 省 / 市 / 详细地址
  const addrParts: string[] = []
  if (p.country) addrParts.push(p.country)
  if (p.region) addrParts.push(p.region)
  if (p.city && p.city !== p.region) addrParts.push(p.city)
  if (p.address && p.address !== p.city && p.address !== p.location_name) {
    addrParts.push(p.address)
  }
  const addrLine = addrParts.length > 0 ? `<div class="pp-addr">${addrParts.join(' · ')}</div>` : ''
  return `
    <div class="pp" data-id="${p.id}">
      <div class="pp-img-wrap"><img class="pp-img" data-id="${p.id}" alt="印章" /></div>
      <div class="pp-title">${loc}</div>
      ${addrLine}
      <div class="pp-meta">
        <span>📅 ${date}</span>
        ${typeBadge}${photoBadge}
      </div>
      <a class="pp-link" href="/timeline">在时间线中查看</a>
    </div>
  `
}

async function fetchPoints() {
  loading.value = true
  error.value = ''
  const params: Record<string, string> = {}
  if (cityFilter.value) params.city = cityFilter.value
  if (typeFilter.value) params.type = typeFilter.value
  try {
    const { data } = await http.get<MapPoint[]>('/api/views/map/points', { params })
    totalCount.value = data.length
    renderMarkers(data)
  } catch (e: any) {
    error.value = e?.response?.data?.detail || '加载失败'
  } finally {
    loading.value = false
  }
}

function renderMarkers(points: MapPoint[]) {
  const m = map.value
  if (!m) return
  // 清掉旧 marker 层
  m.eachLayer((layer) => {
    if (layer instanceof L.Marker) m.removeLayer(layer)
  })

  if (points.length === 0) return

  const bounds: L.LatLngExpression[] = []
  points.forEach((p) => {
    const marker = L.marker([p.latitude, p.longitude], { icon: stampIcon })
    marker.bindPopup(popupHtml(p))
    // 打开 popup 时设置图片 src（含 token 的 URL，浏览器自动加载）
    marker.on('popupopen', () => {
      const img = document.querySelector<HTMLImageElement>(
        `.pp-img[data-id="${p.id}"]`
      )
      if (img && !img.src) {
        img.src = getImageUrl(p.id)
      }
    })
    marker.addTo(m)
    bounds.push([p.latitude, p.longitude])
  })

  // 自动适配视图
  if (bounds.length === 1) {
    m.setView(bounds[0] as L.LatLngExpression, 13)
  } else if (bounds.length > 1) {
    m.fitBounds(L.latLngBounds(bounds as L.LatLngExpression[]), { padding: [40, 40] })
  }
}

// 中国领土近似多边形（顺时针，[lng, lat]），粗略但能正确区分周边国家首都
// 顶点涵盖：帕米尔-新疆-中蒙边界-东北-中朝边界-海岸线-中越中老中缅-中印边界-西藏
const CHINA_BORDER: [number, number][] = [
  [73.5, 39.4], [74.9, 37.2], [76.0, 37.0], [78.6, 35.5], [79.5, 32.3],
  [81.0, 30.2], [82.5, 28.5], [85.0, 28.0], [88.0, 28.0], [92.0, 27.5],
  [95.0, 28.5], [98.2, 27.0], [98.5, 24.5], [97.5, 24.0], [101.0, 21.5],
  [102.0, 21.2], [104.0, 22.5], [105.0, 23.0], [108.0, 21.5], [110.0, 18.2],
  [114.5, 22.2], [119.0, 24.5], [121.5, 29.2], [121.8, 31.2], [122.0, 37.0],
  // 中朝边界：丹东鸭绿江口约 [124.4, 40.1]，向北到长白山
  [124.4, 40.1], [128.0, 41.5], [130.5, 42.5], [133.0, 45.0], [134.0, 48.0],
  [122.5, 53.5], [120.0, 50.0], [116.0, 46.0],
  // 中蒙边界：二连浩特约 [112, 43.65]，边界在 44°N 附近
  [111.0, 44.0], [107.0, 42.0],
  [100.0, 42.0], [96.0, 43.0], [90.0, 47.0], [85.0, 47.0], [80.0, 45.0],
  [78.0, 40.5],
]

// 射线法判断点是否在多边形内
function pointInPolygon(lat: number, lng: number, polygon: [number, number][]): boolean {
  let inside = false
  const n = polygon.length
  for (let i = 0, j = n - 1; i < n; j = i++) {
    const [xi, yi] = polygon[i]
    const [xj, yj] = polygon[j]
    // 判断水平射线 lat 是否穿过边 (i, j)
    if ((yi > lat) !== (yj > lat)) {
      const xIntersect = xi + ((lat - yi) / (yj - yi)) * (xj - xi)
      if (lng < xIntersect) inside = !inside
    }
  }
  return inside
}

// 判断坐标是否在中国境内（边界框快速排除 + 多边形精确判断）
function isDomestic(lat: number, lng: number): boolean {
  // 基础边界框快速排除
  if (lat < 15 || lat > 55 || lng < 70 || lng > 140) return false
  return pointInPolygon(lat, lng, CHINA_BORDER)
}

// 切换激活图层（移除旧激活层、添加新层）
function switchActiveLayer(newLayer: L.TileLayer) {
  const m = map.value
  if (!m) return
  if (activeLayer.value && m.hasLayer(activeLayer.value) && activeLayer.value !== newLayer) {
    m.removeLayer(activeLayer.value)
  }
  if (!m.hasLayer(newLayer)) {
    newLayer.addTo(m)
    // 保证新层在最底层（marker/popup 在上层）
    newLayer.bringToBack()
  }
  activeLayer.value = newLayer
}

// 根据 mode + 当前位置决定应使用的图层
function resolveTargetLayer(): { layer: L.TileLayer; region: 'domestic' | 'overseas' } {
  const m = map.value
  if (!m) {
    return { layer: amapLayer.value!, region: 'domestic' }
  }
  const center = m.getCenter()

  if (layerMode.value === 'street') {
    // 手动街道模式：国内用高德，国外用 ArcGIS 街道
    if (isDomestic(center.lat, center.lng)) {
      return { layer: amapLayer.value!, region: 'domestic' }
    }
    return { layer: arcgisStreetLayer.value!, region: 'overseas' }
  }
  if (layerMode.value === 'satellite') {
    return { layer: arcgisImageryLayer.value!, region: 'overseas' }
  }
  // auto 模式：国内高德矢量，国外 ArcGIS 街道
  if (isDomestic(center.lat, center.lng)) {
    return { layer: amapLayer.value!, region: 'domestic' }
  }
  return { layer: arcgisStreetLayer.value!, region: 'overseas' }
}

// 应用图层切换（含状态同步）
function applyLayerSwitch() {
  const { layer, region } = resolveTargetLayer()
  if (activeLayer.value !== layer) {
    switchActiveLayer(layer)
  }
  currentRegion.value = region
}

// moveend 自动切换（仅 auto / street 模式触发）
function onMapMove() {
  if (layerMode.value === 'satellite') return // 卫星模式锁定
  applyLayerSwitch()
}

// 切换图层模式（用户点击底部浮动栏）
function setMode(mode: LayerMode) {
  layerMode.value = mode
  applyLayerSwitch()
}

function onLogout() {
  auth.logout()
  router.replace('/login')
}

onMounted(() => {
  if (!mapEl.value) return

  // 三层底图
  amapLayer.value = L.tileLayer(
    'https://webrd0{s}.is.autonavi.com/appmaptile?lang=zh_cn&size=1&scale=1&style=8&x={x}&y={y}&z={z}',
    {
      subdomains: '1234',
      attribution: '© 高德地图',
      maxZoom: 18,
    },
  )
  arcgisStreetLayer.value = L.tileLayer(
    'https://server.arcgisonline.com/ArcGIS/rest/services/World_Street_Map/MapServer/tile/{z}/{y}/{x}',
    {
      attribution: '© Esri ArcGIS',
      maxZoom: 19,
    },
  )
  arcgisImageryLayer.value = L.tileLayer(
    'https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}',
    {
      attribution: '© Esri ArcGIS World Imagery',
      maxZoom: 19,
    },
  )

  const m = L.map(mapEl.value, {
    center: [35.0, 105.0],
    zoom: 4,
    zoomControl: true,
    layers: [amapLayer.value],
  })
  activeLayer.value = amapLayer.value
  map.value = m

  // 监听地图移动/缩放：在 auto 模式下根据中心点自动切换图层
  m.on('moveend', onMapMove)

  fetchPoints()
})

onUnmounted(() => {
  map.value?.remove()
  map.value = null
})
</script>

<template>
  <div class="page map-page">
    <header class="header">
      <div>
        <h1 class="page-title">印章地图</h1>
        <p class="subtitle">共 {{ totalCount }} 个盖章点</p>
      </div>
      <div class="header-actions">
        <RouterLink to="/album" class="link">盖章本</RouterLink>
        <RouterLink to="/timeline" class="link">时间线</RouterLink>
        <RouterLink to="/upload" class="add-btn">＋ 新增</RouterLink>
        <button class="secondary" @click="onLogout">登出</button>
      </div>
    </header>

    <section class="filter-bar">
      <input v-model="cityFilter" type="text" placeholder="按城市筛选" @keyup.enter="fetchPoints" />
      <input v-model="typeFilter" type="text" placeholder="按类型筛选" @keyup.enter="fetchPoints" />
      <button @click="fetchPoints" :disabled="loading">筛选</button>
    </section>

    <div class="map-shell">
      <div ref="mapEl" class="map-el"></div>

      <!-- 底部浮动图层切换栏（复古手账风） -->
      <div class="layer-bar" role="tablist" aria-label="地图图层切换">
        <button
          class="layer-tab"
          :class="{ active: layerMode === 'auto' }"
          role="tab"
          :aria-selected="layerMode === 'auto'"
          @click="setMode('auto')"
        >
          <span class="tab-icon">🧭</span>
          <span class="tab-label">自动</span>
          <span class="tab-hint">{{ layerMode === 'auto' ? (currentRegion === 'domestic' ? '高德·国内' : 'ArcGIS·海外') : '智能切换' }}</span>
        </button>
        <button
          class="layer-tab"
          :class="{ active: layerMode === 'street' }"
          role="tab"
          :aria-selected="layerMode === 'street'"
          @click="setMode('street')"
        >
          <span class="tab-icon">🗺</span>
          <span class="tab-label">街道</span>
          <span class="tab-hint">矢量路网</span>
        </button>
        <button
          class="layer-tab"
          :class="{ active: layerMode === 'satellite' }"
          role="tab"
          :aria-selected="layerMode === 'satellite'"
          @click="setMode('satellite')"
        >
          <span class="tab-icon">🛰</span>
          <span class="tab-label">卫星</span>
          <span class="tab-hint">实景影像</span>
        </button>
      </div>

      <p v-if="loading" class="overlay-msg">载入中…</p>
      <p v-else-if="error" class="overlay-msg err">{{ error }}</p>
      <p v-else-if="totalCount === 0 && !loading" class="overlay-msg">
        地图上还没有印章，<RouterLink to="/upload">去盖第一枚</RouterLink>
      </p>
    </div>
  </div>
</template>

<style scoped>
.map-page {
  max-width: 1100px;
}

.header {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 1rem;
  margin-bottom: 0.8rem;
}

.subtitle {
  font-size: 0.8rem;
  color: #8b6f47;
  margin: 0.2rem 0 0;
}

.header-actions {
  display: flex;
  gap: 0.5rem;
  align-items: center;
}

.link,
.add-btn {
  display: inline-block;
  text-decoration: none;
  font-size: 0.9rem;
  padding: 0.45rem 0.9rem;
  border-radius: 6px;
}

.link {
  color: #6b4423;
  border: 1px solid #c9a877;
  background: transparent;
}

.add-btn {
  background: #6b4423;
  color: #f5e6c8;
  border: 1px solid #6b4423;
}

.filter-bar {
  display: flex;
  gap: 0.5rem;
  margin-bottom: 0.8rem;
}

.filter-bar input {
  flex: 1;
  max-width: 220px;
}

.filter-bar button {
  flex: 0 0 auto;
}

.map-shell {
  position: relative;
  border: 1px solid #c9a877;
  border-radius: 10px;
  overflow: hidden;
  background: #f5e6c8;
  box-shadow: 0 4px 16px rgba(61, 40, 23, 0.1);
}

.map-el {
  width: 100%;
  height: 70vh;
  min-height: 420px;
}

/* 底部浮动图层切换栏：默认折叠为小圆点，hover 展开 */
.layer-bar {
  position: absolute;
  left: 50%;
  bottom: 18px;
  transform: translateX(-50%);
  z-index: 1000;
  display: flex;
  gap: 4px;
  padding: 6px;
  background: rgba(251, 241, 221, 0.94);
  border: 1px solid #c9a877;
  border-radius: 14px;
  box-shadow: 0 4px 14px rgba(61, 40, 23, 0.22);
  backdrop-filter: blur(6px);
  -webkit-backdrop-filter: blur(6px);
  transition: width 0.25s ease, height 0.25s ease, padding 0.25s ease,
    gap 0.25s ease, border-radius 0.25s ease, background 0.25s ease,
    box-shadow 0.25s ease;
}

/* 折叠态：收成一个小圆点，所有内容隐藏 */
.layer-bar:not(:hover) {
  width: 12px;
  height: 12px;
  min-width: 12px;
  padding: 0;
  gap: 0;
  border-radius: 50%;
  background: #6b4423;
  border-color: #3d2817;
  box-shadow: 0 1px 4px rgba(61, 40, 23, 0.4);
  overflow: hidden;
}

/* 折叠时隐藏所有 tab 内容 */
.layer-bar:not(:hover) .layer-tab {
  width: 0;
  min-width: 0;
  padding: 0;
  margin: 0;
  border: 0;
  opacity: 0;
  pointer-events: none;
  overflow: hidden;
}

.layer-bar:not(:hover) .layer-tab .tab-icon,
.layer-bar:not(:hover) .layer-tab .tab-label,
.layer-bar:not(:hover) .layer-tab .tab-hint {
  opacity: 0;
  width: 0;
  margin: 0;
  overflow: hidden;
  pointer-events: none;
}

.layer-tab {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 1px;
  min-width: 72px;
  padding: 6px 12px;
  border: 1px solid transparent;
  border-radius: 9px;
  background: transparent;
  color: #6b4423;
  font-family: inherit;
  font-size: 0.85rem;
  cursor: pointer;
  transition: all 0.18s ease, opacity 0.2s ease;
  overflow: hidden;
}

.layer-tab:hover {
  background: rgba(245, 230, 200, 0.7);
  border-color: #d4b88a;
}

.layer-tab.active {
  background: #6b4423;
  color: #f5e6c8;
  border-color: #3d2817;
  box-shadow: inset 0 1px 3px rgba(0, 0, 0, 0.25);
}

.layer-tab.active .tab-hint {
  color: #f5e6c8;
  opacity: 0.85;
}

.tab-icon {
  font-size: 1rem;
  line-height: 1;
}

.tab-label {
  font-weight: 600;
  font-size: 0.82rem;
  line-height: 1.1;
  transition: opacity 0.2s ease;
}

.tab-hint {
  font-size: 0.62rem;
  color: #8b6f47;
  letter-spacing: 0.3px;
  line-height: 1.1;
  transition: opacity 0.2s ease;
}

.overlay-msg {
  position: absolute;
  top: 50%;
  left: 50%;
  transform: translate(-50%, -50%);
  background: rgba(245, 230, 200, 0.92);
  border: 1px dashed #c9a877;
  border-radius: 8px;
  padding: 0.8rem 1.2rem;
  color: #6b4423;
  font-size: 0.9rem;
  z-index: 500;
  pointer-events: auto;
}

.overlay-msg.err {
  color: #b04030;
}

.overlay-msg a {
  color: #6b4423;
  font-weight: 600;
}

/* 复古印章风 marker */
:deep(.stamp-marker) {
  background: transparent;
}

:deep(.stamp-dot) {
  width: 28px;
  height: 28px;
  display: flex;
  align-items: center;
  justify-content: center;
  color: #b04030;
  font-size: 26px;
  text-shadow:
    0 0 1px #fff,
    0 1px 2px rgba(0, 0, 0, 0.3);
  filter: drop-shadow(0 1px 1px rgba(0, 0, 0, 0.4));
}

/* Leaflet popup 复古化 */
:deep(.leaflet-popup-content-wrapper) {
  background: #fbf1dd;
  color: #3d2817;
  border: 1px solid #c9a877;
  border-radius: 8px;
  box-shadow: 0 4px 14px rgba(61, 40, 23, 0.18);
}

:deep(.leaflet-popup-content) {
  margin: 0.6rem 0.7rem;
}

:deep(.leaflet-popup-tip) {
  background: #fbf1dd;
  border: 1px solid #c9a877;
}

:deep(.pp) {
  min-width: 180px;
  font-family: 'Noto Sans SC', sans-serif;
}

:deep(.pp-img-wrap) {
  width: 100%;
  height: 120px;
  background: #f5e6c8;
  border: 1px solid #d4b88a;
  border-radius: 4px;
  overflow: hidden;
  margin-bottom: 0.4rem;
  display: flex;
  align-items: center;
  justify-content: center;
}

:deep(.pp-img) {
  max-width: 100%;
  max-height: 100%;
  object-fit: contain;
}

:deep(.pp-title) {
  font-weight: 600;
  font-size: 0.95rem;
  color: #3d2817;
}

:deep(.pp-addr) {
  font-size: 0.78rem;
  color: #6b4423;
  margin: 0.2rem 0;
  line-height: 1.4;
}

:deep(.pp-meta) {
  font-size: 0.75rem;
  color: #6b4423;
  margin: 0.25rem 0 0.35rem;
  display: flex;
  flex-wrap: wrap;
  gap: 0.3rem;
  align-items: center;
}

:deep(.pp-tag) {
  font-size: 0.65rem;
  border: 1px solid #c9a877;
  border-radius: 3px;
  padding: 0 0.3rem;
  background: #f5e6c8;
  color: #6b4423;
}

:deep(.pp-tag.muted) {
  color: #8b6f47;
}

:deep(.pp-link) {
  display: inline-block;
  font-size: 0.75rem;
  color: #6b4423;
  text-decoration: underline;
}

/* Leaflet zoom 控件复古化 */
:deep(.leaflet-control-zoom a) {
  background: #fbf1dd;
  color: #6b4423;
  border-color: #c9a877;
}

:deep(.leaflet-control-zoom a:hover) {
  background: #f5e6c8;
}

:deep(.leaflet-control-attribution) {
  background: rgba(251, 241, 221, 0.85);
  color: #6b4423;
}

:deep(.leaflet-control-attribution a) {
  color: #6b4423;
}

@media (max-width: 600px) {
  .header {
    flex-direction: column;
    align-items: stretch;
  }
  .header-actions {
    justify-content: flex-end;
  }
  .filter-bar {
    flex-wrap: wrap;
  }
  .filter-bar input {
    max-width: none;
  }
  .map-el {
    height: 60vh;
  }
  .layer-bar {
    bottom: 10px;
    padding: 4px;
  }
  .layer-tab {
    min-width: 60px;
    padding: 5px 8px;
    font-size: 0.78rem;
  }
  .tab-hint {
    display: none;
  }
}
</style>
