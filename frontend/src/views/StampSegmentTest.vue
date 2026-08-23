<script setup lang="ts">
import { ref, onUnmounted } from 'vue'
import { useAuthStore } from '@/stores/auth'

const auth = useAuthStore()

const fileInput = ref<HTMLInputElement>()

// DOM 元素引用
const overlayDiv = ref<HTMLDivElement>()

// 图片与框选状态
const imgSrc = ref('')
const imgNaturalW = ref(0)
const imgNaturalH = ref(0)
const displayScale = ref(1)
// 核心：bbox 存储百分比坐标 (0.0 ~ 1.0)
const bbox = ref<{ x0: number; y0: number; x1: number; y1: number } | null>(null)
const dragging = ref(false)
const dragStartPercent = ref({ x: 0, y: 0 })
const dragEndPercent = ref({ x: 0, y: 0 })

// 颜色与结果
const color = ref<'red' | 'blue' | 'black' | 'auto'>('auto')
const resultUrl = ref('')
const loading = ref(false)
const converting = ref(false)
const errorMsg = ref('')

// 棋盘格背景样式
const checkerBg =
  'linear-gradient(45deg,#ccc 25%,transparent 25%),linear-gradient(-45deg,#ccc 25%,transparent 25%),linear-gradient(45deg,transparent 75%,#ccc 75%),linear-gradient(-45deg,transparent 75%,#ccc 75%)'

// 检测是否 HEIC/HEIF 格式
function isHeic(file: File): boolean {
  const name = file.name.toLowerCase()
  return (
    name.endsWith('.heic') ||
    name.endsWith('.heif') ||
    name.endsWith('.hif') ||
    file.type === 'image/heic' ||
    file.type === 'image/heif'
  )
}

// 把 File 转成浏览器可预览的 blob URL
async function fileToPreviewUrl(file: File): Promise<string> {
  if (isHeic(file)) {
    converting.value = true
    try {
      const heic2any = (await import('heic2any')).default
      const converted = (await heic2any({
        blob: file,
        toType: 'image/jpeg',
        quality: 0.92,
      })) as Blob
      converting.value = false
      return URL.createObjectURL(converted)
    } catch (e) {
      converting.value = false
      throw new Error(`HEIC 转换失败：${e}`)
    }
  }
  return URL.createObjectURL(file)
}

async function onFileChange(e: Event) {
  const target = e.target as HTMLInputElement
  const file = target.files?.[0]
  if (!file) return

  resultUrl.value = ''
  errorMsg.value = ''
  bbox.value = null
  imgSrc.value = ''
  imgNaturalW.value = 0
  imgNaturalH.value = 0
  displayScale.value = 1

  try {
    const url = await fileToPreviewUrl(file)
    imgSrc.value = url
  } catch (e) {
    errorMsg.value = String(e)
  }
}

// 模板中 <img> 的 @load 事件：获取原图尺寸和计算显示比例
function onImgLoad(e: Event) {
  const img = e.target as HTMLImageElement
  imgNaturalW.value = img.naturalWidth
  imgNaturalH.value = img.naturalHeight

  const maxW = 720
  const maxH = 600
  const ratio = Math.min(maxW / img.naturalWidth, maxH / img.naturalHeight, 1)
  displayScale.value = ratio
}

// 获取鼠标相对于 overlay 的百分比坐标
// 关键：使用 e.offsetX/offsetY，或者 getBoundingClientRect 计算
function getPercentPos(e: MouseEvent) {
  const el = overlayDiv.value
  if (!el) return { x: 0, y: 0 }
  
  const rect = el.getBoundingClientRect()
  
  // 钳制坐标在元素范围内
  let x = e.clientX - rect.left
  let y = e.clientY - rect.top
  x = Math.max(0, Math.min(x, rect.width))
  y = Math.max(0, Math.min(y, rect.height))
  
  return {
    x: x / rect.width,
    y: y / rect.height,
  }
}

function onMouseDown(e: MouseEvent) {
  dragging.value = true
  const p = getPercentPos(e)
  dragStartPercent.value = p
  dragEndPercent.value = p
  bbox.value = { x0: p.x, y0: p.y, x1: p.x, y1: p.y }
}

function onMouseMove(e: MouseEvent) {
  if (!dragging.value) return
  const p = getPercentPos(e)
  dragEndPercent.value = p
  bbox.value = {
    x0: dragStartPercent.value.x,
    y0: dragStartPercent.value.y,
    x1: dragEndPercent.value.x,
    y1: dragEndPercent.value.y,
  }
}

function onMouseUp() {
  dragging.value = false
}

function onMouseLeave() {
  dragging.value = false
}

function clearBbox() {
  bbox.value = null
}

async function submit() {
  if (!fileInput.value?.files?.[0]) {
    errorMsg.value = '请先选择图片'
    return
  }

  loading.value = true
  errorMsg.value = ''

  try {
    const fd = new FormData()
    fd.append('file', fileInput.value.files[0])
    fd.append('color', color.value)
    
    // 将百分比坐标转换为原图物理像素坐标
    if (bbox.value) {
      const realX0 = Math.round(Math.min(bbox.value.x0, bbox.value.x1) * imgNaturalW.value)
      const realY0 = Math.round(Math.min(bbox.value.y0, bbox.value.y1) * imgNaturalH.value)
      const realX1 = Math.round(Math.max(bbox.value.x0, bbox.value.x1) * imgNaturalW.value)
      const realY1 = Math.round(Math.max(bbox.value.y0, bbox.value.y1) * imgNaturalH.value)
      
      fd.append('bbox_x0', String(realX0))
      fd.append('bbox_y0', String(realY0))
      fd.append('bbox_x1', String(realX1))
      fd.append('bbox_y1', String(realY1))
    }

    const resp = await fetch('/api/segment-test', {
      method: 'POST',
      headers: { Authorization: `Bearer ${auth.token}` },
      body: fd,
    })

    if (!resp.ok) {
      const data = await resp.json().catch(() => ({ detail: resp.statusText }))
      errorMsg.value = data.detail || '分割失败'
      loading.value = false
      return
    }

    const blob = await resp.blob()
    if (resultUrl.value) URL.revokeObjectURL(resultUrl.value)
    resultUrl.value = URL.createObjectURL(blob)
  } catch (e) {
    errorMsg.value = `请求失败：${e}`
  } finally {
    loading.value = false
  }
}

onUnmounted(() => {
  if (resultUrl.value) URL.revokeObjectURL(resultUrl.value)
})
</script>

<template>
  <div class="page">
    <h1 class="page-title">印章分割测试</h1>
    <p class="desc">
      上传印章照片 → 在图上拖拽框选印章区域 → 选择颜色 → 点击分割。
      <br />不框选则全图自动分割。
    </p>

    <!-- 步骤 1：上传 -->
    <div class="step">
      <label class="step-label">① 选择图片</label>
      <input ref="fileInput" type="file" accept="image/*,.heic,.heif" @change="onFileChange" />
    </div>

    <!-- 步骤 2：框选 -->
    <div v-if="converting" class="step">
      <p class="converting">HEIC 转换中，请稍候...</p>
    </div>
    <div v-if="imgSrc && !converting" class="step">
      <label class="step-label">② 框选印章（可选）</label>
      
      <!-- 关键：使用 DOM 叠加层方案，彻底规避 Canvas 坐标问题 -->
      <div class="image-container" ref="imageContainer">
        <!-- 底层：显示图片 -->
        <img :src="imgSrc" class="preview-img" alt="预览图" @load="onImgLoad" />
        
        <!-- 上层：透明的框选交互层，覆盖在图片上 -->
        <div 
          ref="overlayDiv" 
          class="selection-overlay"
          @mousedown="onMouseDown"
          @mousemove="onMouseMove"
          @mouseup="onMouseUp"
          @mouseleave="onMouseLeave"
        >
          <!-- 框选矩形（动态定位） -->
          <div 
            v-if="bbox" 
            class="selection-box"
            :style="{
              left: Math.min(bbox.x0, bbox.x1) * 100 + '%',
              top: Math.min(bbox.y0, bbox.y1) * 100 + '%',
              width: Math.abs(bbox.x1 - bbox.x0) * 100 + '%',
              height: Math.abs(bbox.y1 - bbox.y0) * 100 + '%',
            }"
          >
            <!-- 尺寸标签 -->
            <span class="box-label">
              {{ Math.round(Math.abs(bbox.x1 - bbox.x0) * imgNaturalW) }} × {{ Math.round(Math.abs(bbox.y1 - bbox.y0) * imgNaturalH) }}
            </span>
          </div>
        </div>
      </div>
      
      <button v-if="bbox" class="secondary clear-btn" @click="clearBbox">清除框选</button>
    </div>

    <!-- 步骤 3：颜色 + 分割 -->
    <div v-if="imgSrc && !converting" class="step">
      <label class="step-label">③ 印章颜色 & 分割</label>
      <div class="color-row">
        <label v-for="c in (['auto','red','blue','black'] as const)" :key="c" class="color-opt">
          <input v-model="color" type="radio" :value="c" />
          <span :class="['color-dot', c === 'auto' ? 'auto' : c]"></span>
          {{ c === 'auto' ? '自动检测' : c === 'red' ? '红色' : c === 'blue' ? '蓝色' : '黑色' }}
        </label>
      </div>
      <button :disabled="loading" @click="submit">
        {{ loading ? '分割中...' : '开始分割' }}
      </button>
      <span v-if="errorMsg" class="error">{{ errorMsg }}</span>
    </div>

    <!-- 结果 -->
    <div v-if="resultUrl" class="step">
      <label class="step-label">④ 分割结果</label>
      <div class="result-wrap" :style="{ backgroundImage: checkerBg, backgroundSize: '16px 16px' }">
        <img :src="resultUrl" ref="resultImg" alt="分割结果" />
      </div>
    </div>
  </div>
</template>

<style scoped>
.page {
  padding: 1.5rem;
  max-width: 800px;
  margin: 0 auto;
}

.page-title {
  color: #6b4423;
  margin-bottom: 0.5rem;
}

.desc {
  color: #8b6f47;
  font-size: 0.85rem;
  margin-bottom: 1.5rem;
}

.converting {
  color: #6b4423;
  font-size: 0.9rem;
  padding: 1rem;
  text-align: center;
  background: #fbf1dd;
  border: 1px solid #c9a877;
  border-radius: 8px;
}

.step {
  margin-bottom: 1.5rem;
}

.step-label {
  display: block;
  font-weight: 600;
  color: #6b4423;
  margin-bottom: 0.5rem;
  font-size: 0.9rem;
}

/* 图片容器：相对定位，作为叠加层的定位参考 */
.image-container {
  position: relative;
  display: inline-block;
  border: 2px solid #c9a877;
  border-radius: 8px;
  background: #fbf1dd;
  max-width: 100%;
  overflow: hidden;
}

/* 预览图片 */
.preview-img {
  display: block;
  max-width: 100%;
  height: auto;
  user-select: none;
  -webkit-user-drag: none;
}

/* 框选交互层：绝对定位，覆盖在图片上 */
.selection-overlay {
  position: absolute;
  top: 0;
  left: 0;
  width: 100%;
  height: 100%;
  cursor: crosshair;
  /* 重要：移除任何可能影响坐标的变换 */
  transform: none;
  box-sizing: border-box;
}

/* 框选矩形 */
.selection-box {
  position: absolute;
  border: 2px dashed #e74c3c;
  background: rgba(231, 76, 60, 0.1);
  box-sizing: border-box;
  pointer-events: none; /* 允许事件穿透到父元素 */
  min-width: 1px;
  min-height: 1px;
}

/* 框选尺寸标签 */
.box-label {
  position: absolute;
  top: -22px;
  left: 0;
  background: #e74c3c;
  color: white;
  padding: 2px 6px;
  font-size: 12px;
  font-weight: bold;
  border-radius: 3px;
  white-space: nowrap;
}

.clear-btn {
  margin-top: 0.5rem;
  font-size: 0.8rem;
  padding: 0.3rem 0.8rem;
}

.color-row {
  display: flex;
  gap: 1.2rem;
  margin-bottom: 0.8rem;
}

.color-opt {
  display: flex;
  align-items: center;
  gap: 0.3rem;
  font-size: 0.85rem;
  cursor: pointer;
}

.color-opt input {
  width: auto;
}

.color-dot {
  display: inline-block;
  width: 14px;
  height: 14px;
  border-radius: 50%;
  border: 1px solid #8b6f47;
}

.color-dot.red {
  background: #c0392b;
}
.color-dot.blue {
  background: #2c3e8f;
}
.color-dot.black {
  background: #1a1a1a;
}
.color-dot.auto {
  background: conic-gradient(#c0392b, #2c3e8f, #1a1a1a, #c0392b);
}

.error {
  color: #c0392b;
  margin-left: 0.8rem;
  font-size: 0.85rem;
}

.result-wrap {
  border: 2px solid #c9a877;
  border-radius: 8px;
  padding: 8px;
  display: inline-block;
  max-width: 100%;
}

.result-wrap img {
  display: block;
  max-width: 100%;
  border-radius: 4px;
}
</style>