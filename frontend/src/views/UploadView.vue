<script setup lang="ts">
import { ref, computed } from 'vue'
import { useRouter } from 'vue-router'
import { http } from '@/api/http'

const router = useRouter()

const file = ref<File | null>(null)
const previewUrl = ref<string>('')
const fileName = ref<string>('')

const stampDate = ref<string>('')
const locationName = ref<string>('')
const address = ref<string>('')
const city = ref<string>('')
const region = ref<string>('')
const latitude = ref<string>('')
const longitude = ref<string>('')
const type = ref<string>('')
const notes = ref<string>('')
const isPhotoOnly = ref(false)

const submitting = ref(false)
const error = ref('')
const success = ref(false)
const exifLoading = ref(false)
const exifInfo = ref<string>('')

const canSubmit = computed(() => !!file.value && !submitting.value)

async function onFileChange(e: Event) {
  const input = e.target as HTMLInputElement
  const f = input.files?.[0]
  if (!f) return
  file.value = f
  fileName.value = f.name
  if (previewUrl.value) URL.revokeObjectURL(previewUrl.value)
  previewUrl.value = URL.createObjectURL(f)
  error.value = ''
  success.value = false
  exifInfo.value = ''
  await previewExif(f)
}

async function onDrop(e: DragEvent) {
  e.preventDefault()
  const f = e.dataTransfer?.files?.[0]
  if (!f) return
  if (!f.type.startsWith('image/')) {
    error.value = '请选择图片文件'
    return
  }
  file.value = f
  fileName.value = f.name
  if (previewUrl.value) URL.revokeObjectURL(previewUrl.value)
  previewUrl.value = URL.createObjectURL(f)
  error.value = ''
  exifInfo.value = ''
  await previewExif(f)
}

async function previewExif(f: File) {
  exifLoading.value = true
  try {
    const form = new FormData()
    form.append('file', f)
    const { data } = await http.post<any>('/api/stamps/preview-exif', form, {
      headers: { 'Content-Type': 'multipart/form-data' },
    })
    if (data.stamp_date && !stampDate.value) {
      stampDate.value = data.stamp_date
    }
    if (data.exif_has_gps) {
      latitude.value = String(data.latitude)
      longitude.value = String(data.longitude)
      if (data.location_name && !locationName.value) {
        locationName.value = data.location_name
      }
      if (data.address && !address.value) {
        address.value = data.address
      }
      if (data.city && !city.value) {
        city.value = data.city
      }
      if (data.region && !region.value) {
        region.value = data.region
      }
      exifInfo.value = '✓ 已自动提取位置信息'
    } else if (data.exif_has_date) {
      exifInfo.value = '✓ 已自动提取拍摄日期（无 GPS 位置信息）'
    } else {
      exifInfo.value = '⚠ 照片无 EXIF 信息，请手动填写'
    }
  } catch {
    exifInfo.value = '⚠ 无法解析照片信息，请手动填写'
  } finally {
    exifLoading.value = false
  }
}

function onDragOver(e: DragEvent) {
  e.preventDefault()
}

async function onSubmit() {
  if (!file.value) {
    error.value = '请先选择印章图片'
    return
  }
  error.value = ''
  success.value = false
  submitting.value = true

  const form = new FormData()
  form.append('file', file.value)
  if (stampDate.value) form.append('stamp_date', stampDate.value)
  if (locationName.value) form.append('location_name', locationName.value)
  if (address.value) form.append('address', address.value)
  if (city.value) form.append('city', city.value)
  if (region.value) form.append('region', region.value)
  if (latitude.value) form.append('latitude', latitude.value)
  if (longitude.value) form.append('longitude', longitude.value)
  if (type.value) form.append('type', type.value)
  if (notes.value) form.append('notes', notes.value)
  if (isPhotoOnly.value) form.append('is_photo_only', 'true')

  try {
    await http.post('/api/stamps', form, {
      headers: { 'Content-Type': 'multipart/form-data' },
    })
    success.value = true
    setTimeout(() => router.push('/timeline'), 800)
  } catch (e: any) {
    error.value = e?.response?.data?.detail || '上传失败，请重试'
  } finally {
    submitting.value = false
  }
}

function reset() {
  file.value = null
  fileName.value = ''
  if (previewUrl.value) URL.revokeObjectURL(previewUrl.value)
  previewUrl.value = ''
  locationName.value = ''
  address.value = ''
  city.value = ''
  region.value = ''
  latitude.value = ''
  longitude.value = ''
  type.value = ''
  notes.value = ''
  isPhotoOnly.value = false
  error.value = ''
  success.value = false
  exifInfo.value = ''
  exifLoading.value = false
}
</script>

<template>
  <div class="page">
    <header class="header">
      <h1 class="page-title">新增印章</h1>
      <RouterLink to="/timeline" class="back">← 返回时间线</RouterLink>
    </header>

    <div class="upload-grid">
      <!-- 左：图片选择与预览 -->
      <section class="preview-box">
        <div
          class="drop-zone"
          :class="{ 'has-img': !!previewUrl }"
          @drop="onDrop"
          @dragover="onDragOver"
        >
          <img v-if="previewUrl" :src="previewUrl" alt="预览" class="preview-img" />
          <div v-else class="placeholder">
            <div class="ph-icon">📷</div>
            <p>点击或拖拽图片至此</p>
            <p class="ph-hint">支持 JPG / PNG / WEBP / HEIC</p>
          </div>
        </div>
        <label class="file-btn">
          选择图片
          <input type="file" accept="image/*" @change="onFileChange" hidden />
        </label>
        <p v-if="fileName" class="file-name">{{ fileName }}</p>
        <p v-if="exifLoading" class="exif-status">⏳ 正在分析照片信息…</p>
        <p v-else-if="exifInfo" class="exif-status" :class="{ warn: exifInfo.startsWith('⚠') }">{{ exifInfo }}</p>
      </section>

      <!-- 右：表单 -->
      <section class="form-box">
        <div class="row">
          <label class="field">
            <span class="label">盖章日期</span>
            <input v-model="stampDate" type="date" placeholder="留空取照片 EXIF" />
            <span class="hint">留空则自动取照片拍摄日期</span>
          </label>
          <label class="field">
            <span class="label">类型</span>
            <input v-model="type" type="text" placeholder="如：风景/纪念/景点" />
          </label>
        </div>

        <label class="field">
          <span class="label">地点名称</span>
          <input v-model="locationName" type="text" placeholder="如：故宫博物院" />
        </label>

        <label class="field">
          <span class="label">详细地址</span>
          <input v-model="address" type="text" placeholder="街道门牌等" />
        </label>

        <div class="row">
          <label class="field">
            <span class="label">城市</span>
            <input v-model="city" type="text" placeholder="如：北京" />
          </label>
          <label class="field">
            <span class="label">区域</span>
            <input v-model="region" type="text" placeholder="如：华北" />
          </label>
        </div>

        <div class="row">
          <label class="field">
            <span class="label">纬度</span>
            <input v-model="latitude" type="text" placeholder="可选" />
          </label>
          <label class="field">
            <span class="label">经度</span>
            <input v-model="longitude" type="text" placeholder="可选" />
          </label>
        </div>

        <label class="field">
          <span class="label">备注</span>
          <textarea v-model="notes" rows="3" placeholder="当时的感受或小故事…"></textarea>
        </label>

        <label class="checkbox">
          <input v-model="isPhotoOnly" type="checkbox" />
          <span>仅作照片打卡（无实体印章）</span>
        </label>

        <p v-if="error" class="error">{{ error }}</p>
        <p v-if="success" class="success">✓ 已收藏！正在跳转…</p>

        <div class="actions">
          <button class="secondary" type="button" @click="reset" :disabled="submitting">重置</button>
          <button type="button" class="primary" :disabled="!canSubmit" @click="onSubmit">
            {{ submitting ? '上传中…' : '收入集章本' }}
          </button>
        </div>
      </section>
    </div>
  </div>
</template>

<style scoped>
.header {
  display: flex;
  align-items: baseline;
  justify-content: space-between;
  margin-bottom: 1.2rem;
}

.back {
  font-size: 0.85rem;
  text-decoration: none;
  color: #6b4423;
}

.upload-grid {
  display: grid;
  grid-template-columns: 1fr 1.2fr;
  gap: 1.5rem;
}

@media (max-width: 720px) {
  .upload-grid {
    grid-template-columns: 1fr;
  }
}

.preview-box {
  background: #fbf1dd;
  border: 1px solid #c9a877;
  border-radius: 10px;
  padding: 1rem;
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 0.75rem;
}

.drop-zone {
  width: 100%;
  aspect-ratio: 1 / 1;
  border: 2px dashed #c9a877;
  border-radius: 8px;
  display: flex;
  align-items: center;
  justify-content: center;
  overflow: hidden;
  background: #f5e6c8;
  transition: border-color 0.2s;
}

.drop-zone.has-img {
  border-style: solid;
  border-color: #6b4423;
}

.preview-img {
  width: 100%;
  height: 100%;
  object-fit: contain;
}

.placeholder {
  text-align: center;
  color: #8b6f47;
}

.ph-icon {
  font-size: 2.4rem;
}

.ph-hint {
  font-size: 0.75rem;
  margin-top: 0.3rem;
  color: #a08560;
}

.file-btn {
  display: inline-block;
  cursor: pointer;
  border: 1px solid #6b4423;
  background: #6b4423;
  color: #f5e6c8;
  padding: 0.45rem 1rem;
  border-radius: 6px;
  font-size: 0.9rem;
}

.file-name {
  font-size: 0.8rem;
  color: #6b4423;
  word-break: break-all;
  text-align: center;
  margin: 0;
}

.exif-status {
  font-size: 0.75rem;
  color: #5a7a3a;
  margin: 0;
  text-align: center;
}

.exif-status.warn {
  color: #b07030;
}

.form-box {
  background: #fbf1dd;
  border: 1px solid #c9a877;
  border-radius: 10px;
  padding: 1.1rem;
  display: flex;
  flex-direction: column;
  gap: 0.7rem;
}

.row {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 0.7rem;
}

.field {
  display: flex;
  flex-direction: column;
  gap: 0.25rem;
}

.label {
  font-size: 0.8rem;
  color: #6b4423;
}

.hint {
  font-size: 0.7rem;
  color: #a08560;
  margin-top: 0.15rem;
}

.checkbox {
  display: flex;
  align-items: center;
  gap: 0.4rem;
  font-size: 0.85rem;
  color: #3d2817;
  cursor: pointer;
}

.checkbox input {
  width: auto;
}

.error {
  margin: 0;
  color: #b04030;
  font-size: 0.85rem;
}

.success {
  margin: 0;
  color: #5a7a3a;
  font-size: 0.85rem;
}

.actions {
  display: flex;
  gap: 0.6rem;
  margin-top: 0.3rem;
}

.primary {
  flex: 1;
}
</style>
