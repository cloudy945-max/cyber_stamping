/** 后端 /api/stats/* 响应类型。 */

export interface Overview {
  total: number
  cities: number
  regions: number
  photo_only: number
  with_sticker: number
  earliest_date: string | null
  latest_date: string | null
}

export interface MonthBucket {
  month: string  // YYYY-MM
  count: number
}

export interface TypeBucket {
  type: string
  count: number
}

export interface RegionBucket {
  region: string
  count: number
}
