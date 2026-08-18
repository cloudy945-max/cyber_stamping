export interface Stamp {
  id: number
  original_path: string
  sticker_path: string | null
  process_status: string
  stamp_date: string | null
  location_name: string | null
  address: string | null
  city: string | null
  region: string | null
  latitude: number | null
  longitude: number | null
  type: string | null
  notes: string | null
  is_photo_only: boolean
}
