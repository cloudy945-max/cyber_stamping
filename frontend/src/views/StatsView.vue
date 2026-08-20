<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'
import { http } from '@/api/http'
import { useAuthStore } from '@/stores/auth'
import StatsChart from '@/components/StatsChart.vue'
import type { Overview, MonthBucket, RegionBucket, TypeBucket } from '@/types/stats'

const router = useRouter()
const auth = useAuthStore()

const overview = ref<Overview | null>(null)
const months = ref<MonthBucket[]>([])
const types = ref<TypeBucket[]>([])
const regions = ref<RegionBucket[]>([])

const loading = ref(false)
const error = ref('')

async function fetchAll() {
  loading.value = true
  error.value = ''
  try {
    const [ov, bm, bt, br] = await Promise.all([
      http.get<Overview>('/api/stats/overview'),
      http.get<MonthBucket[]>('/api/stats/by-month'),
      http.get<TypeBucket[]>('/api/stats/by-type'),
      http.get<RegionBucket[]>('/api/stats/by-region'),
    ])
    overview.value = ov.data
    months.value = bm.data
    types.value = bt.data
    regions.value = br.data
  } catch (e: any) {
    error.value = e?.response?.data?.detail || '加载失败'
  } finally {
    loading.value = false
  }
}

/* ---- 图表 option ---- */

// 复古手账风配色
const PALETTE = ['#C8403C', '#6B4423', '#8B6F47', '#C9A877', '#A0522D', '#D2691E', '#CD853F', '#8B4513']

const monthOption = computed(() => ({
  tooltip: { trigger: 'axis' },
  grid: { left: 40, right: 20, top: 20, bottom: 40 },
  xAxis: {
    type: 'category',
    data: months.value.map((m) => m.month),
    axisLabel: { color: '#6B4423', rotate: 45, fontSize: 10 },
    axisLine: { lineStyle: { color: '#C9A877' } },
  },
  yAxis: {
    type: 'value',
    minInterval: 1,
    axisLabel: { color: '#6B4423' },
    splitLine: { lineStyle: { color: '#E8D8B5' } },
  },
  series: [
    {
      type: 'line',
      smooth: true,
      symbol: 'circle',
      symbolSize: 6,
      data: months.value.map((m) => m.count),
      itemStyle: { color: '#C8403C' },
      lineStyle: { color: '#C8403C', width: 2 },
      areaStyle: {
        color: {
          type: 'linear',
          x: 0, y: 0, x2: 0, y2: 1,
          colorStops: [
            { offset: 0, color: 'rgba(200,64,60,0.25)' },
            { offset: 1, color: 'rgba(200,64,60,0)' },
          ],
        },
      },
    },
  ],
}))

const typeOption = computed(() => ({
  tooltip: { trigger: 'item', formatter: '{b}: {c} ({d}%)' },
  legend: {
    orient: 'vertical',
    right: 10,
    top: 'center',
    textStyle: { color: '#6B4423', fontSize: 12 },
  },
  series: [
    {
      type: 'pie',
      radius: ['40%', '70%'],
      center: ['40%', '50%'],
      avoidLabelOverlap: true,
      itemStyle: { borderColor: '#FBF1DD', borderWidth: 2 },
      label: { show: true, color: '#3D2817', formatter: '{b}\n{c} 枚' },
      data: types.value.map((t, i) => ({
        name: t.type,
        value: t.count,
        itemStyle: { color: PALETTE[i % PALETTE.length] },
      })),
    },
  ],
}))

const regionOption = computed(() => ({
  tooltip: { trigger: 'axis', axisPointer: { type: 'shadow' } },
  grid: { left: 80, right: 20, top: 20, bottom: 30 },
  xAxis: {
    type: 'value',
    minInterval: 1,
    axisLabel: { color: '#6B4423' },
    splitLine: { lineStyle: { color: '#E8D8B5' } },
  },
  yAxis: {
    type: 'category',
    data: regions.value.map((r) => r.region).reverse(),
    axisLabel: { color: '#6B4423' },
    axisLine: { lineStyle: { color: '#C9A877' } },
  },
  series: [
    {
      type: 'bar',
      data: regions.value.map((r) => r.count).reverse(),
      barWidth: '55%',
      itemStyle: {
        color: '#8B6F47',
        borderRadius: [0, 4, 4, 0],
      },
      label: { show: true, position: 'right', color: '#6B4423' },
    },
  ],
}))

const photoRate = computed(() => {
  if (!overview.value || overview.value.total === 0) return 0
  return Math.round((overview.value.photo_only / overview.value.total) * 100)
})

const stickerRate = computed(() => {
  if (!overview.value || overview.value.total === 0) return 0
  return Math.round((overview.value.with_sticker / overview.value.total) * 100)
})

function onLogout() {
  auth.logout()
  router.replace('/login')
}

onMounted(fetchAll)
</script>

<template>
  <div class="page">
    <header class="header">
      <div>
        <h1 class="page-title">集章统计</h1>
        <p class="subtitle" v-if="overview">
          {{ overview.earliest_date || '—' }} ~ {{ overview.latest_date || '—' }}
        </p>
      </div>
      <div class="header-actions">
        <RouterLink to="/timeline" class="nav-btn">时间线</RouterLink>
        <RouterLink to="/map" class="nav-btn">地图</RouterLink>
        <RouterLink to="/upload" class="add-btn">＋ 新增</RouterLink>
        <button class="secondary" @click="onLogout">登出</button>
      </div>
    </header>

    <p v-if="loading" class="status">载入中…</p>
    <p v-else-if="error" class="error">{{ error }}</p>

    <template v-if="!loading && !error && overview">
      <!-- 总览卡片 -->
      <section class="overview-grid">
        <div class="metric-card">
          <div class="metric-value">{{ overview.total }}</div>
          <div class="metric-label">印章总数</div>
        </div>
        <div class="metric-card">
          <div class="metric-value">{{ overview.cities }}</div>
          <div class="metric-label">城市</div>
        </div>
        <div class="metric-card">
          <div class="metric-value">{{ overview.regions }}</div>
          <div class="metric-label">省/地区</div>
        </div>
        <div class="metric-card">
          <div class="metric-value">{{ overview.with_sticker }}</div>
          <div class="metric-label">已抠图贴纸</div>
          <div class="metric-sub">覆盖率 {{ stickerRate }}%</div>
        </div>
        <div class="metric-card">
          <div class="metric-value">{{ overview.photo_only }}</div>
          <div class="metric-label">仅照片打卡</div>
          <div class="metric-sub">占比 {{ photoRate }}%</div>
        </div>
      </section>

      <!-- 月份趋势 -->
      <section class="chart-card">
        <h2 class="chart-title">月份趋势</h2>
        <StatsChart :option="monthOption" height="300px" />
      </section>

      <!-- 类型 + 地区 -->
      <section class="charts-row">
        <div class="chart-card half">
          <h2 class="chart-title">类型分布</h2>
          <StatsChart :option="typeOption" height="280px" />
        </div>
        <div class="chart-card half">
          <h2 class="chart-title">地区 Top</h2>
          <StatsChart :option="regionOption" height="280px" />
        </div>
      </section>
    </template>
  </div>
</template>

<style scoped>
.header {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 1rem;
  margin-bottom: 1.2rem;
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
  flex-wrap: wrap;
}

.nav-btn {
  text-decoration: none;
  border: 1px solid #c9a877;
  background: transparent;
  color: #6b4423;
  padding: 0.55rem 1.1rem;
  border-radius: 6px;
  font-size: 0.9rem;
}

.add-btn {
  display: inline-block;
  text-decoration: none;
  border: 1px solid #6b4423;
  background: #6b4423;
  color: #f5e6c8;
  padding: 0.55rem 1.1rem;
  border-radius: 6px;
  font-size: 0.9rem;
}

.status,
.error {
  text-align: center;
  padding: 2rem 1rem;
  color: #6b4423;
}

.overview-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(130px, 1fr));
  gap: 0.8rem;
  margin-bottom: 1.5rem;
}

.metric-card {
  background: #fbf1dd;
  border: 1px solid #d4b88a;
  border-radius: 8px;
  padding: 0.9rem 0.7rem;
  text-align: center;
  display: flex;
  flex-direction: column;
  gap: 0.2rem;
}

.metric-value {
  font-size: 1.8rem;
  font-weight: 700;
  color: #6b4423;
  font-family: 'Noto Serif SC', serif;
  line-height: 1.1;
}

.metric-label {
  font-size: 0.8rem;
  color: #8b6f47;
}

.metric-sub {
  font-size: 0.7rem;
  color: #c8403c;
  margin-top: 0.1rem;
}

.chart-card {
  background: #fbf1dd;
  border: 1px solid #d4b88a;
  border-radius: 8px;
  padding: 0.9rem 1rem 1rem;
  margin-bottom: 1.2rem;
}

.chart-title {
  font-size: 1rem;
  color: #6b4423;
  margin: 0 0 0.6rem;
  font-family: 'Noto Serif SC', serif;
}

.charts-row {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 1rem;
}

.chart-card.half {
  margin-bottom: 0;
}

@media (max-width: 700px) {
  .header {
    flex-direction: column;
    align-items: stretch;
  }
  .header-actions {
    justify-content: flex-end;
  }
  .charts-row {
    grid-template-columns: 1fr;
  }
}
</style>
