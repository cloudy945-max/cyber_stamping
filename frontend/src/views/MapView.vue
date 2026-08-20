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
  city: string | null
  stamp_date: string | null
  is_photo_only: boolean
}

const router = useRouter()
const auth = useAuthStore()

const mapEl = ref<HTMLDivElement | null>(null)
const map = shallowRef<L.Map | null>(null)
const loading = ref(false)
const error = ref('')
const totalCount = ref(0)
const cityFilter = ref('')
const typeFilter = ref('')

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
  return `
    <div class="pp" data-id="${p.id}">
      <div class="pp-img-wrap"><img class="pp-img" data-id="${p.id}" alt="印章" /></div>
      <div class="pp-title">${loc}</div>
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

function onLogout() {
  auth.logout()
  router.replace('/login')
}

onMounted(() => {
  if (!mapEl.value) return
  // 高德矢量瓦片（开源 Leaflet 不绑 SDK）
  const amapLayer = L.tileLayer(
    'https://webrd0{s}.is.autonavi.com/appmaptile?lang=zh_cn&size=1&scale=1&style=8&x={x}&y={y}&z={z}',
    {
      subdomains: '1234',
      attribution: '© 高德地图',
      maxZoom: 18,
    },
  )
  const m = L.map(mapEl.value, {
    center: [35.0, 105.0],
    zoom: 4,
    zoomControl: true,
    layers: [amapLayer],
  })
  map.value = m
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
}
</style>
