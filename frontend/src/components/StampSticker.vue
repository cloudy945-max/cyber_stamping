<script setup lang="ts">
import { computed } from 'vue'
import { stampImageUrl } from '@/utils/image'
import type { Stamp } from '@/types/stamp'

const props = defineProps<{
  stamp: Stamp
  /** 贴纸尺寸（像素） */
  size?: number
  /** 是否显示手写注释 */
  showNote?: boolean
}>()

const size = computed(() => props.size ?? 120)
const showNote = computed(() => props.showNote ?? true)

/** 微旋转角度：基于印章 id 确定性生成 -3° ~ +3° */
const rotation = computed(() => {
  const seed = (props.stamp.id * 7 + 13) % 100
  return -3 + (seed / 100) * 6
})

/** 优先使用抠图贴纸，降级为原图 */
const imageSrc = computed(() => {
  if (props.stamp.sticker_path && props.stamp.process_status === 'done') {
    return stampImageUrl(props.stamp.id, 'sticker')
  }
  return stampImageUrl(props.stamp.id, 'original')
})

const locationLabel = computed(() => {
  return props.stamp.location_name || '未命名地点'
})

const dateLabel = computed(() => {
  return props.stamp.stamp_date || ''
})

const typeLabel = computed(() => {
  return props.stamp.type || ''
})
</script>

<template>
  <div
    class="sticker"
    :style="{
      transform: `rotate(${rotation}deg)`,
      width: `${size}px`,
      height: `${size}px`,
    }"
  >
    <img
      :src="imageSrc"
      :alt="locationLabel"
      class="sticker-img"
      draggable="false"
    />
    <div v-if="showNote" class="sticker-note">
      <span v-if="dateLabel" class="note-date">{{ dateLabel }}</span>
      <span class="note-loc">{{ locationLabel }}</span>
      <span v-if="typeLabel" class="note-type">{{ typeLabel }}</span>
    </div>
  </div>
</template>

<style scoped>
.sticker {
  position: relative;
  display: inline-flex;
  flex-direction: column;
  align-items: center;
  transition: transform 0.2s ease;
}

.sticker:hover {
  transform: rotate(0deg) scale(1.05) !important;
  z-index: 10;
}

.sticker-img {
  width: 100%;
  height: 100%;
  object-fit: contain;
  filter: drop-shadow(1px 2px 3px rgba(60, 40, 20, 0.35));
  pointer-events: none;
  user-select: none;
}

.sticker-note {
  margin-top: 0.35rem;
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 0.05rem;
  font-family: 'Ma Shan Zheng', 'Noto Serif SC', cursive;
  line-height: 1.2;
}

.note-date {
  font-size: 0.7rem;
  color: #8b6f47;
}

.note-loc {
  font-size: 0.8rem;
  color: #3d2817;
  font-weight: 600;
  max-width: 120px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.note-type {
  font-size: 0.6rem;
  color: #c8403c;
  border: 1px solid #c8403c;
  border-radius: 3px;
  padding: 0 0.25rem;
  margin-top: 0.1rem;
}
</style>
