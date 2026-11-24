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
  slots: number
  expected: number
  coverage: number | null
  median_gap: number | null
  max_gap: number | null
}

export type Criterion = {
  id: string
  name: string
  how: string
  line: string
  value: string | null
  ok: boolean | null
  fallback: string
  source: string
  min_days?: number
}

export type Errs = { known: number; unknown: number; naive: number }

export type PlanResult = {
  park: string
  date: string | null
  entry: string
  exit: string
  ll_use_until: string
  wait_source: string
  slack_min: number
  steps: { time: string; kind: string; name: string; tag: string; wait: number; walk: number; note: string }[]
  skipped: { name: string; priority: number }[]
  multi_pass: {
    no: string; name: string; priority: number; demand: string | null; rank: number | null; take: boolean
    book?: string; return?: string; use?: string; standby_then?: number; why?: string
  }[]
  with_ll: { rides: number; shows: number; wait_min: number; end: string; missed: string[] }
  without_ll: { rides: number; shows: number; wait_min: number; end: string; missed: string[] } | null
}

export type ParkData = {
  park: string
  park_name: string
  generated_at: string
  range: { from: string; to: string; days: number; rows: number; last_fetch: string | null; coverage: number | null }
  days: Day[]
  rides: Ride[]
  unmatched: { id: number; name: string }[]
  not_analyzed?: { id: number; name: string; kind: 'station' | 'show' | 'experience' | 'single_rider'; parent: number | null; note: string | null; qt_name: string | null }[]
  attribution: { text: string; url: string }
  // 分析計画書に合わせた部分
  data_days: number
  special: Record<string, { label: string; from: string; to: string }>
  crowd_index: Record<'all' | 'ex_thanksgiving' | 'ex_christmas' | 'ex_both', Record<string, number>> | null
  q3: {
    rides: Record<string, { name: string; a: number; b: number; r2: number; days: number; shape: [number, number][] }>
    gbm_importance: { name: string; value: number }[]
  } | null
  q4: {
    backtest: {
      days: number; all: Errs; top: Errs
      per_day: { date: string; ci_true: number | null; ci_guess: number; err: number }[]
      rides: ({ no: string; name: string; n: number } & Errs)[]
    } | null
    gbm: { method: string; all: number; top: number | null; bands: Record<string, number | null> }[] | null
  } | null
  q5: {
    k: number; silhouette: number; ari: number; k_scores: Record<string, number>
    groups: { id: number; name: string; members: { no: string; name: string; mean: number; confidence: number | null; silhouette: number }[] }[]
  } | null
  q6: { rank: number; group: number; no: string; name: string; early: number; mid: number; p_open: number; saved: number }[] | null
  q7: {
    no: string; name: string; p_day: number; events_per_day: number; avg_min: number; p_morning_down: number; days: number
    start_hours: Record<string, number>; p_hour: Record<string, number>
  }[] | null
  q8: {
    shows: { show: string; time: string; no: number; name: string; before: number | null; during: number | null; change: number | null; days: number }[]
    occupancy: { blocks: number[]; rides: { no: number; name: string; share: Record<string, number | null> }[] }
  }
  criteria: Criterion[]
  outputs: Record<'model' | 'backtest' | 'gbm' | 'insights' | 'plan', { file: string; at: string | null; days: number | null }>
  plan: PlanResult | null
}
