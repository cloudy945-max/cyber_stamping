<script setup lang="ts">
import { onMounted, ref, computed, watch } from 'vue'
import { useRouter } from 'vue-router'
import { http } from '@/api/http'
import { useAuthStore } from '@/stores/auth'
import type { Stamp } from '@/types/stamp'

const router = useRouter()
const auth = useAuthStore()

const stamps = ref<Stamp[]>([])
const loading = ref(false)
const error = ref('')

const page = ref(1)
const pageSize = ref(20)
const hasMore = ref(false)

const filters = ref({
  q: '',
  city: '',
  type: '',
  date_from: '',
  date_to: '',
})

const appliedFilters = ref({ ...filters.value })

async function fetchStamps() {
  loading.value = true
  error.value = ''
  try {
    const params: Record<string, string | number> = {
      page: page.value,
      page_size: pageSize.value,
    }
    for (const [k, v] of Object.entries(appliedFilters.value)) {
      if (v) params[k] = v
    }
    const { data } = await http.get<Stamp[]>('/api/stamps', { params })
    stamps.value = data
    // 后端无 total 字段：以是否满页判断是否可能有更多
    hasMore.value = data.length === pageSize.value
  } catch (e: any) {
    error.value = e?.response?.data?.detail || '加载失败'
  } finally {
    loading.value = false
  }
}

function applyFilters() {
  appliedFilters.value = { ...filters.value }
  page.value = 1
  fetchStamps()
}

function resetFilters() {
  filters.value = { q: '', city: '', type: '', date_from: '', date_to: '' }
  appliedFilters.value = { ...filters.value }
  page.value = 1
  fetchStamps()
}

function prevPage() {
  if (page.value > 1) {
    page.value -= 1
    fetchStamps()
  }
}

function nextPage() {
  if (hasMore.value) {
    page.value += 1
    fetchStamps()
  }
}

const grouped = computed(() => {
  const m = new Map<string, Stamp[]>()
  for (const s of stamps.value) {
    const key = s.stamp_date || '未知日期'
    if (!m.has(key)) m.set(key, [])
    m.get(key)!.push(s)
  }
  return Array.from(m.entries())
})

function imageUrl(id: number) {
  return `/api/stamps/${id}/image?variant=original`
}

function onLogout() {
  auth.logout()
  router.replace('/login')
}

onMounted(fetchStamps)
watch(page, fetchStamps)
</script>

<template>
  <div class="page">
    <header class="header">
      <div>
        <h1 class="page-title">集章时间线</h1>
        <p class="subtitle">共 {{ stamps.length }} 条记录{{ hasMore ? '（当前页可能未完）' : '' }}</p>
      </div>
      <div class="header-actions">
        <RouterLink to="/upload" class="add-btn">＋ 新增印章</RouterLink>
        <button class="secondary" @click="onLogout">登出</button>
      </div>
    </header>

    <!-- 筛选 -->
    <section class="filter-box">
      <div class="filter-row">
        <input v-model="filters.q" type="text" placeholder="关键词（地点名/备注）" />
        <input v-model="filters.city" type="text" placeholder="城市" />
        <input v-model="filters.type" type="text" placeholder="类型" />
      </div>
      <div class="filter-row">
        <input v-model="filters.date_from" type="date" placeholder="起始日期" />
        <span class="dash">至</span>
        <input v-model="filters.date_to" type="date" placeholder="结束日期" />
        <button class="secondary" @click="resetFilters">重置</button>
        <button @click="applyFilters">筛选</button>
      </div>
    </section>

    <!-- 状态 -->
    <p v-if="loading" class="status">载入中…</p>
    <p v-else-if="error" class="error">{{ error }}</p>
    <p v-else-if="stamps.length === 0" class="empty">
      集章本还是空的，<RouterLink to="/upload">去盖第一枚印章</RouterLink> 吧
    </p>

    <!-- 列表 -->
    <section v-if="!loading && stamps.length > 0" class="timeline">
      <article v-for="[dateKey, items] in grouped" :key="dateKey" class="day-group">
        <h2 class="day-title">
          <span class="dot">●</span>
          {{ dateKey }}
        </h2>
        <div class="day-items">
          <div v-for="s in items" :key="s.id" class="stamp-card">
            <div class="thumb">
              <img :src="imageUrl(s.id)" :alt="s.location_name || '印章'" loading="lazy" />
            </div>
            <div class="meta">
              <div class="meta-title">
                <span v-if="s.location_name" class="loc">{{ s.location_name }}</span>
                <span v-else class="loc muted">未命名地点</span>
                <span v-if="s.type" class="tag">{{ s.type }}</span>
                <span v-if="s.is_photo_only" class="tag muted">仅照片</span>
              </div>
              <div v-if="s.city || s.region" class="meta-sub">
                <span v-if="s.city">{{ s.city }}</span>
                <span v-if="s.city && s.region"> · </span>
                <span v-if="s.region">{{ s.region }}</span>
              </div>
              <div v-if="s.address" class="meta-sub muted">{{ s.address }}</div>
              <p v-if="s.notes" class="notes">{{ s.notes }}</p>
            </div>
          </div>
        </div>
      </article>
    </section>

    <!-- 分页 -->
    <nav v-if="stamps.length > 0" class="pagination">
      <button class="secondary" :disabled="page === 1 || loading" @click="prevPage">上一页</button>
      <span class="page-num">第 {{ page }} 页</span>
      <button :disabled="!hasMore || loading" @click="nextPage">下一页</button>
    </nav>
  </div>
</template>

<style scoped>
.header {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 1rem;
  margin-bottom: 1rem;
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

.filter-box {
  background: #fbf1dd;
  border: 1px solid #c9a877;
  border-radius: 8px;
  padding: 0.8rem;
  display: flex;
  flex-direction: column;
  gap: 0.6rem;
  margin-bottom: 1.4rem;
}

.filter-row {
  display: flex;
  gap: 0.5rem;
  align-items: center;
  flex-wrap: wrap;
}

.filter-row input {
  flex: 1;
  min-width: 120px;
}

.dash {
  color: #6b4423;
  font-size: 0.85rem;
}

.status,
.error,
.empty {
  text-align: center;
  padding: 2rem 1rem;
  font-size: 0.95rem;
  color: #6b4423;
}

.empty a {
  color: #6b4423;
  font-weight: 600;
}

.timeline {
  display: flex;
  flex-direction: column;
  gap: 1.5rem;
}

.day-group {
  position: relative;
  padding-left: 1.2rem;
  border-left: 2px solid #c9a877;
}

.day-title {
  display: flex;
  align-items: center;
  gap: 0.4rem;
  font-size: 1rem;
  color: #6b4423;
  margin: 0 0 0.8rem;
  background: #f5e6c8;
  position: relative;
  left: -1.45rem;
  padding-left: 0.25rem;
}

.day-title .dot {
  color: #6b4423;
  font-size: 0.7rem;
}

.day-items {
  display: flex;
  flex-direction: column;
  gap: 0.8rem;
}

.stamp-card {
  display: flex;
  gap: 0.85rem;
  background: #fbf1dd;
  border: 1px solid #d4b88a;
  border-radius: 8px;
  padding: 0.7rem;
}

.thumb {
  flex: 0 0 100px;
  width: 100px;
  height: 100px;
  border: 1px solid #c9a877;
  border-radius: 6px;
  overflow: hidden;
  background: #f5e6c8;
}

.thumb img {
  width: 100%;
  height: 100%;
  object-fit: contain;
}

.meta {
  flex: 1;
  min-width: 0;
  display: flex;
  flex-direction: column;
  gap: 0.2rem;
}

.meta-title {
  display: flex;
  align-items: baseline;
  gap: 0.4rem;
  flex-wrap: wrap;
}

.loc {
  font-weight: 600;
  color: #3d2817;
  font-size: 0.95rem;
}

.loc.muted {
  color: #8b6f47;
  font-weight: 400;
}

.tag {
  font-size: 0.7rem;
  color: #6b4423;
  border: 1px solid #c9a877;
  border-radius: 4px;
  padding: 0.05rem 0.4rem;
  background: #f5e6c8;
}

.tag.muted {
  color: #8b6f47;
}

.meta-sub {
  font-size: 0.8rem;
  color: #6b4423;
}

.meta-sub.muted {
  color: #8b6f47;
}

.notes {
  margin: 0.3rem 0 0;
  font-size: 0.85rem;
  color: #3d2817;
  line-height: 1.5;
  white-space: pre-wrap;
  word-break: break-word;
}

.pagination {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 1rem;
  margin-top: 1.5rem;
}

.page-num {
  font-size: 0.9rem;
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
  .stamp-card {
    flex-direction: column;
  }
  .thumb {
    flex: 0 0 auto;
    width: 100%;
    height: 200px;
  }
}
</style>
