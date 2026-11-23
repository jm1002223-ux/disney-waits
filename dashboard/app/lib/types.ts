// export_dashboard.py が書き出すJSONの形
export type Slot = [slot: number, median: number | null, p90: number | null]

export type Ride = {
  no: number
  name: string
  ll: 'multi' | 'single' | null
  ll_demand: string | null
  avg: number | null
  max: number | null
  uptime: number | null
  down_count: number
  down_min: number
  peak: { time: string; wait: number } | null
  best: { time: string; wait: number } | null
  latest: { open: boolean; wait: number | null; time: string } | null
  profile: { all?: Slot[]; weekday?: Slot[]; weekend?: Slot[] }
  hourly: [hour: number, median: number | null][]
}

export type Day = {
  date: string
  weekday: string
  is_weekend: boolean
  holiday: string | null
  event: string | null
  open: string | null
  close: string | null
  crowd_index: number | null
  runs: number
  expected: number
  coverage: number | null
  median_gap: number | null
  max_gap: number | null
}

export type ParkData = {
  park: string
  park_name: string
  generated_at: string
  range: { from: string; to: string; days: number; rows: number; last_fetch: string | null; coverage: number | null }
  days: Day[]
  rides: Ride[]
  unmatched: { id: number; name: string }[]
  attribution: { text: string; url: string }
}
