<script setup lang="ts">
import { onMounted, ref, computed } from 'vue'
import { useRouter } from 'vue-router'
import { http } from '@/api/http'
import { useAuthStore } from '@/stores/auth'
import StampSticker from '@/components/StampSticker.vue'
import type { Stamp } from '@/types/stamp'

const router = useRouter()
const auth = useAuthStore()

const stamps = ref<Stamp[]>([])
const loading = ref(false)
const error = ref('')
const activeRegion = ref<string>('all')

async function fetchStamps() {
  loading.value = true
  error.value = ''
  try {
    const { data } = await http.get<Stamp[]>('/api/stamps', { params: { page_size: 500 } })
    stamps.value = data
  } catch (e: any) {
    error.value = e?.response?.data?.detail || '加载失败'
  } finally {
    loading.value = false
  }
}

/** 可用地区列表 */
const regionChips = computed(() => {
  const regions = new Set<string>()
  for (const s of stamps.value) {
    if (s.region) regions.add(s.region)
  }
  return Array.from(regions).sort()
})

/** 当前显示的印章 */
const visibleStamps = computed(() => {
  if (activeRegion.value === 'all') return stamps.value
  return stamps.value.filter((s) => s.region === activeRegion.value)
})

/** 按城市分组当前印章 */
const groupedByCity = computed(() => {
  const m = new Map<string, Stamp[]>()
  for (const s of visibleStamps.value) {
    const key = s.city || '未分类'
    if (!m.has(key)) m.set(key, [])
    m.get(key)!.push(s)
  }
  return Array.from(m.entries()).sort((a, b) => a[0].localeCompare(b[0], 'zh'))
})

function onLogout() {
  auth.logout()
  router.replace('/login')
}

onMounted(fetchStamps)
</script>

<template>
  <div class="album-page">
    <!-- 顶部导航 -->
    <header class="album-header">
      <div class="header-left">
        <h1 class="album-title">
          <span class="title-seal">📖</span>
          我的集章本
        </h1>
        <p class="album-sub">
          共 {{ stamps.length }} 枚印章 · {{ regionChips.length }} 个地区
        </p>
      </div>
      <div class="header-actions">
        <RouterLink to="/timeline" class="nav-link">📅 时间线</RouterLink>
        <RouterLink to="/map" class="nav-link">🗺 地图</RouterLink>
        <RouterLink to="/stats" class="nav-link">📊 统计</RouterLink>
        <RouterLink to="/upload" class="nav-link add-link">＋ 盖章</RouterLink>
        <button class="logout-btn" @click="onLogout">登出</button>
      </div>
    </header>

    <!-- 地区筛选 -->
    <section v-if="regionChips.length > 0" class="region-chips">
      <button
        class="chip"
        :class="{ active: activeRegion === 'all' }"
        @click="activeRegion = 'all'"
      >
        全部
      </button>
      <button
        v-for="r in regionChips"
        :key="r"
        class="chip"
        :class="{ active: activeRegion === r }"
        @click="activeRegion = r"
      >
        {{ r }}
      </button>
    </section>

    <!-- 状态 -->
    <p v-if="loading" class="album-status">翻开集章本中…</p>
    <p v-else-if="error" class="album-error">{{ error }}</p>
    <p v-else-if="stamps.length === 0" class="album-empty">
      集章本还是空的，<RouterLink to="/upload">去盖第一枚印章</RouterLink> 吧
    </p>

    <!-- 集章册主体 -->
    <div v-else-if="visibleStamps.length > 0" class="album-book">
      <!-- 左装订孔 -->
      <div class="binding-holes">
        <span v-for="n in 8" :key="n" class="binding-hole" />
      </div>

      <!-- 内页内容 -->
      <div class="album-inner">
        <!-- 封面装饰 -->
        <div class="album-cover">
          <div class="cover-deco-top" />
          <div class="cover-title">
            <span class="cover-cn">旅行集章</span>
            <span class="cover-en">Travel Stamp Album</span>
          </div>
          <div class="cover-deco-bottom" />
        </div>

        <!-- 按城市分组的网格 -->
        <section v-for="[city, items] in groupedByCity" :key="city" class="city-section">
          <h2 class="city-header">
            <span class="city-line" />
            <span class="city-name">{{ city }}</span>
            <span class="city-line" />
            <span class="city-count">{{ items.length }} 枚</span>
          </h2>
          <div class="stamp-grid">
            <div
              v-for="s in items"
              :key="s.id"
              class="stamp-slot"
            >
              <StampSticker :stamp="s" :size="110" />
            </div>
          </div>
        </section>

        <!-- 空白页脚装饰 -->
        <div class="album-footer">
          <span class="footer-text">— 愿每一枚印章都是一段回忆 —</span>
        </div>
      </div>
    </div>
  </div>
</template>

<style scoped>
.album-page {
  min-height: 100vh;
  background: #f5e6c8;
  background-image:
    radial-gradient(ellipse at 20% 30%, rgba(139, 111, 71, 0.08) 0%, transparent 50%),
    radial-gradient(ellipse at 80% 70%, rgba(107, 68, 35, 0.06) 0%, transparent 50%);
  padding-bottom: 3rem;
}

/* ========== 顶部导航 ========== */
.album-header {
  max-width: 820px;
  margin: 0 auto;
  padding: 1.5rem 1.2rem 1rem;
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 1rem;
}

.album-title {
  margin: 0;
  font-family: 'Noto Serif SC', serif;
  font-size: 1.5rem;
  color: #6b4423;
  letter-spacing: 0.1em;
}

.title-seal {
  margin-right: 0.3rem;
}

.album-sub {
  margin: 0.3rem 0 0;
  font-size: 0.85rem;
  color: #8b6f47;
}

.header-actions {
  display: flex;
  gap: 0.5rem;
  align-items: center;
  flex-wrap: wrap;
}

.nav-link {
  display: inline-block;
  text-decoration: none;
  border: 1px solid #c9a877;
  background: transparent;
  color: #6b4423;
  padding: 0.5rem 0.9rem;
  border-radius: 6px;
  font-size: 0.85rem;
  transition: all 0.15s ease;
}

.nav-link:hover {
  background: #6b4423;
  color: #f5e6c8;
}

.nav-link.add-link {
  background: #6b4423;
  color: #f5e6c8;
  border-color: #6b4423;
}

.logout-btn {
  font-size: 0.85rem;
  padding: 0.4rem 0.8rem;
}

/* ========== 地区筛选 ========== */
.region-chips {
  max-width: 820px;
  margin: 0 auto;
  padding: 0 1.2rem 1rem;
  display: flex;
  gap: 0.5rem;
  flex-wrap: wrap;
}

.chip {
  display: inline-block;
  padding: 0.3rem 0.85rem;
  border: 1px solid #c9a877;
  border-radius: 16px;
  font-size: 0.8rem;
  color: #6b4423;
  background: #fbf1dd;
  cursor: pointer;
  transition: all 0.15s ease;
  user-select: none;
  font-family: inherit;
  margin: 0;
}

.chip:hover {
  border-color: #6b4423;
}

.chip.active {
  background: #6b4423;
  color: #f5e6c8;
  border-color: #6b4423;
}

/* ========== 状态提示 ========== */
.album-status,
.album-error,
.album-empty {
  max-width: 820px;
  margin: 0 auto;
  text-align: center;
  padding: 2rem 1rem;
  color: #6b4423;
}

.album-error {
  color: #c8403c;
}

.album-empty a {
  color: #6b4423;
  font-weight: 600;
}

/* ========== 集章册主体 ========== */
.album-book {
  max-width: 820px;
  margin: 0 auto;
  display: flex;
  position: relative;
}

/* 左装订孔 */
.binding-holes {
  width: 28px;
  flex-shrink: 0;
  display: flex;
  flex-direction: column;
  align-items: center;
  padding: 1rem 0.3rem;
  background: linear-gradient(to right, #d4b88a, #e5cca0);
  border-radius: 4px 0 0 4px;
  gap: 1.8rem;
}

.binding-hole {
  width: 14px;
  height: 14px;
  border-radius: 50%;
  background: #f5e6c8;
  box-shadow:
    inset 1px 1px 2px rgba(60, 40, 20, 0.35),
    0 1px 2px rgba(255, 255, 255, 0.5);
}

/* 内页 */
.album-inner {
  flex: 1;
  background: #fbf1dd;
  background-image:
    repeating-linear-gradient(
      0deg,
      transparent,
      transparent 28px,
      rgba(139, 111, 71, 0.03) 28px,
      rgba(139, 111, 71, 0.03) 29px
    );
  padding: 1.5rem 1.5rem 2rem;
  border: 2px solid #8b6f47;
  border-left: none;
  border-radius: 0 8px 8px 0;
  box-shadow:
    0 2px 8px rgba(60, 40, 20, 0.1),
    inset 0 0 40px rgba(139, 111, 71, 0.05);
}

/* 封面装饰 */
.album-cover {
  text-align: center;
  padding: 1rem 0 1.5rem;
  border-bottom: 1px dashed #c9a877;
  margin-bottom: 1.5rem;
  position: relative;
}

.cover-deco-top,
.cover-deco-bottom {
  display: block;
  height: 1px;
  background: linear-gradient(
    to right,
    transparent,
    #8b6f47 20%,
    #6b4423 50%,
    #8b6f47 80%,
    transparent
  );
  margin: 0.5rem auto;
  width: 60%;
}

.cover-title {
  padding: 0.8rem 0;
}

.cover-cn {
  display: block;
  font-family: 'Noto Serif SC', serif;
  font-size: 1.6rem;
  color: #6b4423;
  letter-spacing: 0.3em;
}

.cover-en {
  display: block;
  font-size: 0.75rem;
  color: #8b6f47;
  letter-spacing: 0.2em;
  margin-top: 0.3rem;
  font-family: serif;
}

/* 城市分组 */
.city-section {
  margin-bottom: 2rem;
}

.city-header {
  display: flex;
  align-items: center;
  gap: 0.8rem;
  margin: 0 0 1rem;
  font-family: 'Noto Serif SC', serif;
}

.city-line {
  flex: 1;
  height: 1px;
  background: linear-gradient(
    to right,
    transparent,
    #c9a877,
    transparent
  );
}

.city-name {
  font-size: 1.1rem;
  color: #3d2817;
  font-weight: 600;
  padding: 0 0.5rem;
  background: #fbf1dd;
  position: relative;
}

.city-count {
  font-size: 0.7rem;
  color: #8b6f47;
  border: 1px solid #c9a877;
  border-radius: 10px;
  padding: 0.1rem 0.6rem;
}

/* 贴纸网格 */
.stamp-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(130px, 1fr));
  gap: 1.5rem 1rem;
  padding: 0.5rem;
}

.stamp-slot {
  display: flex;
  justify-content: center;
  align-items: flex-start;
  padding: 0.5rem;
  position: relative;
}

.stamp-slot::before {
  content: '';
  position: absolute;
  top: 0;
  left: 50%;
  transform: translateX(-50%);
  width: 80%;
  height: 2px;
  background: repeating-linear-gradient(
    90deg,
    #8b6f47,
    #8b6f47 4px,
    transparent 4px,
    transparent 8px
  );
  opacity: 0.3;
}

/* 页脚 */
.album-footer {
  text-align: center;
  padding: 1.5rem 0 0.5rem;
  border-top: 1px dashed #c9a877;
  margin-top: 2rem;
}

.footer-text {
  font-family: 'Ma Shan Zheng', 'Noto Serif SC', cursive;
  font-size: 0.9rem;
  color: #8b6f47;
  letter-spacing: 0.15em;
}

@media (max-width: 600px) {
  .album-header {
    flex-direction: column;
    align-items: stretch;
  }
  .header-actions {
    justify-content: flex-start;
  }
  .stamp-grid {
    grid-template-columns: repeat(auto-fill, minmax(100px, 1fr));
    gap: 1.2rem 0.5rem;
  }
  .binding-holes {
    width: 20px;
    gap: 1.4rem;
  }
  .binding-hole {
    width: 10px;
    height: 10px;
  }
}
</style>
