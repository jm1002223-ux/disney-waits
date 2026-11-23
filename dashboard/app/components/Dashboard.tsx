'use client'

import { useMemo, useState } from 'react'
import {
  Area, Bar, BarChart, CartesianGrid, ComposedChart, Line, ReferenceLine, ResponsiveContainer, Tooltip, XAxis, YAxis,
} from 'recharts'
import { AlertTriangle, CalendarDays, CheckCircle2, Database, Gauge, Timer } from 'lucide-react'
import type { Day, ParkData, Ride } from '../lib/types'

// 色:ティール1色を軸にする(系列は常に1つずつ表示するので、分類色は使わない)
const C = {
  line: '#2dd4bf',          // teal-400:中央値の線
  band: 'rgba(45,212,191,0.16)',
  bar: '#14b8a6',           // teal-500
  grid: '#27272a',
  axis: '#71717a',
  good: '#0ca30c',
  warn: '#fab219',
}
// ヒートマップ:待ち時間が長いほど明るい(暗い面では暗い方が「少ない」)
const HEAT = ['#10241d', '#134e4a', '#115e59', '#0f766e', '#0d9488', '#14b8a6', '#2dd4bf', '#99f6e4']
const HEAT_CUTS = [10, 20, 30, 45, 60, 90, 120]
const heatColor = (v: number | null | undefined) => (v == null ? 'transparent' : HEAT[HEAT_CUTS.filter(c => v >= c).length])

const hm = (m: number) => `${Math.floor(m / 60)}:${String(m % 60).padStart(2, '0')}`
const pct = (v: number | null | undefined) => (v == null ? '-' : `${Math.round(v * 100)}%`)
const md = (d: string) => `${Number(d.slice(5, 7))}/${Number(d.slice(8, 10))}`
const llLabel = (r: Ride) => (r.ll === 'multi' ? 'マルチ' : r.ll === 'single' ? 'シングル' : '-')

type Kind = 'all' | 'weekday' | 'weekend'
const KIND_LABEL: Record<Kind, string> = { all: '全日', weekday: '平日', weekend: '週末' }

function Card({ title, note, children, className = '' }: { title: string; note?: React.ReactNode; children: React.ReactNode; className?: string }) {
  return (
    <section className={`min-w-0 bg-zinc-900/50 border border-zinc-800/70 rounded-2xl p-4 sm:p-5 space-y-4 ${className}`}>
      <div className="flex flex-wrap items-baseline justify-between gap-2">
        <h2 className="text-sm font-semibold text-zinc-100">{title}</h2>
        {note && <div className="text-xs text-zinc-500">{note}</div>}
      </div>
      {children}
    </section>
  )
}

function Tile({ icon, label, value, sub }: { icon: React.ReactNode; label: string; value: React.ReactNode; sub?: React.ReactNode }) {
  return (
    <div className="bg-zinc-900/60 border border-zinc-800/80 rounded-2xl p-4">
      <div className="flex items-center gap-1.5 text-xs text-zinc-500">{icon}{label}</div>
      <div className="mt-1.5 text-2xl font-bold text-white tabular-nums">{value}</div>
      {sub && <div className="mt-0.5 text-xs text-zinc-500">{sub}</div>}
    </div>
  )
}

function Segmented<T extends string>({ value, options, onChange }: { value: T; options: [T, string][]; onChange: (v: T) => void }) {
  return (
    <div className="inline-flex rounded-xl border border-zinc-800 bg-zinc-900/60 p-0.5">
      {options.map(([v, label]) => (
        <button key={v} onClick={() => onChange(v)}
          className={`px-3 py-1 text-xs rounded-lg transition-colors ${value === v ? 'bg-teal-500/15 text-teal-300' : 'text-zinc-400 hover:text-zinc-200'}`}>
          {label}
        </button>
      ))}
    </div>
  )
}

function TipBox({ children }: { children: React.ReactNode }) {
  return <div className="bg-zinc-900 border border-zinc-700 rounded-xl px-3 py-2 text-xs shadow-xl space-y-0.5">{children}</div>
}

function Status({ ok, children }: { ok: boolean; children: React.ReactNode }) {
  const Icon = ok ? CheckCircle2 : AlertTriangle
  return (
    <span className="inline-flex items-center gap-1 text-zinc-200">
      <Icon size={12} color={ok ? C.good : C.warn} aria-label={ok ? '基準以上' : '基準未満'} />
      {children}
    </span>
  )
}

/* ── 日別の混雑指数 ───────────────────────── */
function CrowdChart({ days }: { days: Day[] }) {
  const data = days.filter(d => d.crowd_index != null).map(d => ({ ...d, label: `${md(d.date)}${d.weekday}` }))
  if (!data.length) return <p className="text-xs text-zinc-500">混雑指数はデータが3日分ほどたまると出ます。</p>
  return (
    <ResponsiveContainer width="100%" height={200}>
      <BarChart data={data} margin={{ top: 8, right: 8, bottom: 0, left: -16 }}>
        <CartesianGrid strokeDasharray="3 3" stroke={C.grid} vertical={false} />
        <XAxis dataKey="label" tick={{ fontSize: 10, fill: C.axis }} tickLine={false} axisLine={{ stroke: C.grid }} />
        <YAxis tick={{ fontSize: 10, fill: C.axis }} tickLine={false} axisLine={false} />
        <ReferenceLine y={100} stroke="#a1a1aa" strokeDasharray="4 4"
          label={{ value: '期間平均 100', position: 'insideTopRight', fill: '#a1a1aa', fontSize: 10 }} />
        <Tooltip cursor={{ fill: 'rgba(255,255,255,0.04)' }} content={({ active, payload }) => {
          if (!active || !payload?.length) return null
          const d = payload[0].payload as Day & { label: string }
          return (
            <TipBox>
              <p className="font-semibold text-zinc-100">{d.label}{d.holiday ? `・${d.holiday}` : ''}</p>
              <p className="text-zinc-300">混雑指数 {d.crowd_index}</p>
              <p className="text-zinc-500">営業(推定){d.open}〜{d.close}</p>
              {d.event && <p className="text-zinc-500">{d.event}</p>}
            </TipBox>
          )
        }} />
        <Bar dataKey="crowd_index" fill={C.bar} radius={[4, 4, 0, 0]} maxBarSize={28} />
      </BarChart>
    </ResponsiveContainer>
  )
}

/* ── 時間帯ごとの待ち時間 ───────────────────── */
function ProfileChart({ ride, kind }: { ride: Ride; kind: Kind }) {
  const slots = ride.profile[kind] ?? []
  const data = slots.map(([t, med, p90]) => ({ t, med, band: med != null && p90 != null ? [med, p90] : null, p90 }))
  if (data.length < 2) return <p className="text-xs text-zinc-500">この条件のデータがまだありません。</p>
  const t0 = Math.floor(data[0].t / 60) * 60
  const t1 = Math.ceil(data[data.length - 1].t / 60) * 60
  const ticks: number[] = []
  for (let t = t0; t <= t1; t += 120) ticks.push(t)
  return (
    <ResponsiveContainer width="100%" height={260}>
      <ComposedChart data={data} margin={{ top: 8, right: 12, bottom: 0, left: -16 }}>
        <CartesianGrid strokeDasharray="3 3" stroke={C.grid} vertical={false} />
        <XAxis dataKey="t" type="number" domain={[t0, t1]} ticks={ticks} tickFormatter={hm}
          tick={{ fontSize: 10, fill: C.axis }} tickLine={false} axisLine={{ stroke: C.grid }} />
        <YAxis tick={{ fontSize: 10, fill: C.axis }} tickLine={false} axisLine={false} unit="分" />
        <Tooltip cursor={{ stroke: '#52525b', strokeWidth: 1 }} content={({ active, payload }) => {
          if (!active || !payload?.length) return null
          const d = payload[0].payload as (typeof data)[number]
          return (
            <TipBox>
              <p className="font-semibold text-zinc-100">{hm(d.t)}〜</p>
              <p className="text-zinc-300">中央値 {d.med ?? '-'}分</p>
              <p className="text-zinc-500">90%点 {d.p90 ?? '-'}分(10回に1回はこれ以上)</p>
            </TipBox>
          )
        }} />
        <Area type="monotone" dataKey="band" stroke="none" fill={C.band} isAnimationActive={false} activeDot={false} />
        <Line type="monotone" dataKey="med" stroke={C.line} strokeWidth={2} dot={false}
          activeDot={{ r: 4, fill: C.line, stroke: '#0d1f17', strokeWidth: 2 }} isAnimationActive={false} />
      </ComposedChart>
    </ResponsiveContainer>
  )
}

/* ── ヒートマップ(アトラクション × 時) ───────────── */
function Heatmap({ rides, selected, onSelect }: { rides: Ride[]; selected: number; onSelect: (no: number) => void }) {
  const [hover, setHover] = useState<{ name: string; h: number; v: number | null } | null>(null)
  const hours = useMemo(() => {
    const hs = rides.flatMap(r => r.hourly.map(([h]) => h))
    if (!hs.length) return []
    const a = Math.min(...hs), b = Math.max(...hs)
    return Array.from({ length: b - a + 1 }, (_, i) => a + i)
  }, [rides])
  return (
    <div className="space-y-3">
      <div className="flex flex-wrap items-center justify-between gap-3 text-xs">
        <div className="text-zinc-400 min-h-4">
          {hover ? <>{hover.name}・{hover.h}時台・中央値 <span className="text-zinc-100 font-semibold">{hover.v ?? '-'}分</span></> : '行を押すと上のグラフに切り替わります'}
        </div>
        <div className="flex items-center gap-1 text-zinc-500">
          <span>短い</span>
          {HEAT.slice(1).map((c, i) => <span key={c} className="w-4 h-3 rounded-sm" style={{ background: c }} title={i === 0 ? `${HEAT_CUTS[0]}分〜` : `${HEAT_CUTS[i]}分〜`} />)}
          <span>長い(分)</span>
        </div>
      </div>
      <div className="overflow-x-auto">
        <table className="text-xs border-separate" style={{ borderSpacing: 2 }}>
          <thead>
            <tr>
              <th className="sticky left-0 bg-[#141f1b] z-10" />
              {hours.map(h => <th key={h} className="font-normal text-zinc-500 w-7 text-center">{h}</th>)}
            </tr>
          </thead>
          <tbody>
            {rides.map(r => {
              const byH = new Map(r.hourly)
              const sel = r.no === selected
              return (
                <tr key={r.no} onClick={() => onSelect(r.no)} className="cursor-pointer group">
                  <td className={`sticky left-0 z-10 bg-[#141f1b] pr-3 py-0.5 whitespace-nowrap max-w-56 truncate ${sel ? 'text-teal-300 font-semibold' : 'text-zinc-400 group-hover:text-zinc-200'}`}>
                    {r.no}. {r.name}
                  </td>
                  {hours.map(h => {
                    const v = byH.get(h)
                    return (
                      <td key={h} className="w-7 h-5 rounded-[4px]"
                        style={{ background: heatColor(v), outline: sel ? '1px solid rgba(45,212,191,0.35)' : undefined }}
                        onMouseEnter={() => setHover({ name: r.name, h, v: v ?? null })} onMouseLeave={() => setHover(null)} />
                    )
                  })}
                </tr>
              )
            })}
          </tbody>
        </table>
      </div>
    </div>
  )
}

/* ── 一覧表 ─────────────────────────── */
function RideTable({ rides, selected, onSelect }: { rides: Ride[]; selected: number; onSelect: (no: number) => void }) {
  return (
    <div className="overflow-x-auto">
      <table className="w-full text-xs">
        <thead className="text-zinc-500">
          <tr className="border-b border-zinc-800">
            {['アトラクション', 'パス', '平均', 'ピーク', '空く時刻', '稼働率', 'シス調', '最後の取得'].map((h, i) => (
              <th key={h} className={`py-2 px-2 font-normal ${i === 0 ? 'text-left' : 'text-right'} whitespace-nowrap`}>{h}</th>
            ))}
          </tr>
        </thead>
        <tbody>
          {rides.map(r => (
            <tr key={r.no} onClick={() => onSelect(r.no)}
              className={`border-b border-zinc-800/50 cursor-pointer ${r.no === selected ? 'bg-teal-500/[0.07]' : 'hover:bg-white/[0.02]'}`}>
              <td className="py-1.5 px-2 text-zinc-200 whitespace-nowrap">{r.no}. {r.name}</td>
              <td className="py-1.5 px-2 text-right text-zinc-400">{llLabel(r)}</td>
              <td className="py-1.5 px-2 text-right tabular-nums text-zinc-100">{r.avg != null ? `${Math.round(r.avg)}分` : '-'}</td>
              <td className="py-1.5 px-2 text-right tabular-nums text-zinc-300 whitespace-nowrap">{r.peak ? `${r.peak.time}(${Math.round(r.peak.wait)}分)` : '-'}</td>
              <td className="py-1.5 px-2 text-right tabular-nums text-zinc-300 whitespace-nowrap">{r.best ? `${r.best.time}(${Math.round(r.best.wait)}分)` : '-'}</td>
              <td className="py-1.5 px-2 text-right tabular-nums text-zinc-300">{pct(r.uptime)}</td>
              <td className="py-1.5 px-2 text-right tabular-nums text-zinc-300 whitespace-nowrap">{r.down_count ? `${r.down_count}回・${r.down_min}分` : '-'}</td>
              <td className="py-1.5 px-2 text-right tabular-nums text-zinc-500 whitespace-nowrap">
                {r.latest ? `${r.latest.time} ${r.latest.open ? `${r.latest.wait ?? 0}分` : '休止'}` : '-'}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}

/* ── データ品質 ─────────────────────────── */
function QualityTable({ d }: { d: ParkData }) {
  return (
    <div className="space-y-3">
      <div className="overflow-x-auto">
        <table className="w-full text-xs">
          <thead className="text-zinc-500">
            <tr className="border-b border-zinc-800">
              {['日付', '営業(推定)', '取得回数', '充足率', '間隔(中央・最大)', '混雑指数'].map((h, i) => (
                <th key={h} className={`py-2 px-2 font-normal ${i === 0 ? 'text-left' : 'text-right'} whitespace-nowrap`}>{h}</th>
              ))}
            </tr>
          </thead>
          <tbody>
            {d.days.map(x => (
              <tr key={x.date} className="border-b border-zinc-800/50">
                <td className="py-1.5 px-2 text-zinc-200 whitespace-nowrap">{md(x.date)}({x.weekday}){x.holiday ? ` ${x.holiday}` : ''}</td>
                <td className="py-1.5 px-2 text-right tabular-nums text-zinc-400 whitespace-nowrap">{x.open ? `${x.open}〜${x.close}` : '-'}</td>
                <td className="py-1.5 px-2 text-right tabular-nums text-zinc-300 whitespace-nowrap">{x.runs} / {x.expected}</td>
                <td className="py-1.5 px-2 text-right tabular-nums">
                  {x.coverage == null ? '-' : <Status ok={x.coverage >= 0.9}>{pct(x.coverage)}</Status>}
                </td>
                <td className="py-1.5 px-2 text-right tabular-nums text-zinc-400 whitespace-nowrap">{x.median_gap ?? '-'}分・{x.max_gap ?? '-'}分</td>
                <td className="py-1.5 px-2 text-right tabular-nums text-zinc-300">{x.crowd_index ?? '-'}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      {d.unmatched.length > 0 && (
        <p className="text-xs text-zinc-400">
          <AlertTriangle size={12} className="inline mr-1" color={C.warn} aria-label="注意" />
          rides.json にない名前({d.unmatched.length}件):{d.unmatched.map(u => u.name).join('、')}
        </p>
      )}
    </div>
  )
}

/* ── 全体 ─────────────────────────────── */
export function Dashboard({ parks }: { parks: ParkData[] }) {
  const [parkId, setParkId] = useState(parks[0].park)
  const d = parks.find(p => p.park === parkId) ?? parks[0]
  const [rideNo, setRideNo] = useState<Record<string, number>>({})
  const [kind, setKind] = useState<Kind>('all')
  const ride = d.rides.find(r => r.no === rideNo[d.park]) ?? d.rides[0]
  const select = (no: number) => setRideNo(s => ({ ...s, [d.park]: no }))
  const cov = d.range.coverage

  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <h1 className="text-xl font-bold text-white">{d.park_name}</h1>
          <p className="text-xs text-zinc-500 mt-1">現地時間(太平洋時間)で表示。待ち時間は営業中の表示値の集計です</p>
        </div>
        <Segmented value={parkId} options={parks.map(p => [p.park, p.park] as [string, string])} onChange={setParkId} />
      </div>

      <div className="grid grid-cols-2 lg:grid-cols-4 gap-3">
        <Tile icon={<CalendarDays size={12} />} label="集計期間" value={`${d.range.days}日分`} sub={`${md(d.range.from)}〜${md(d.range.to)}`} />
        <Tile icon={<Gauge size={12} />} label="データ充足率(平均)"
          value={cov == null ? '-' : <Status ok={cov >= 0.9}><span className="text-2xl">{pct(cov)}</span></Status>} sub="合格ライン 90%" />
        <Tile icon={<Database size={12} />} label="記録" value={d.range.rows.toLocaleString()} sub={`アトラクション ${d.rides.length}`} />
        <Tile icon={<Timer size={12} />} label="最後の取得(現地)" value={d.range.last_fetch?.slice(11) ?? '-'} sub={d.range.last_fetch?.slice(0, 10)} />
      </div>

      <Card title="時間帯ごとの待ち時間" note="線=中央値、帯=中央値〜90%点(15分ごと)">
        <div className="flex flex-wrap items-center gap-2">
          <select value={ride.no} onChange={e => select(Number(e.target.value))}
            className="bg-zinc-900 border border-zinc-800 rounded-xl px-3 py-1.5 text-xs text-zinc-200 max-w-full">
            {d.rides.map(r => <option key={r.no} value={r.no}>{r.no}. {r.name}</option>)}
          </select>
          <Segmented value={kind} options={(Object.keys(KIND_LABEL) as Kind[]).map(k => [k, KIND_LABEL[k]])} onChange={setKind} />
        </div>
        <ProfileChart ride={ride} kind={kind} />
        <div className="flex flex-wrap gap-x-6 gap-y-1 text-xs text-zinc-400">
          <span>空く時刻 <span className="text-zinc-100">{ride.best ? `${ride.best.time}(${Math.round(ride.best.wait)}分)` : '-'}</span></span>
          <span>ピーク <span className="text-zinc-100">{ride.peak ? `${ride.peak.time}(${Math.round(ride.peak.wait)}分)` : '-'}</span></span>
          <span>パス <span className="text-zinc-100">{llLabel(ride)}</span></span>
          <span>稼働率 <span className="text-zinc-100">{pct(ride.uptime)}</span></span>
        </div>
      </Card>

      <Card title="日別の混雑指数" note="人気アトラクションの日平均 ÷ 期間平均 × 100">
        <CrowdChart days={d.days} />
      </Card>

      <Card title="アトラクション × 時間帯" note="各時台の中央値(平均待ちの長い順)">
        <Heatmap rides={d.rides} selected={ride.no} onSelect={select} />
      </Card>

      <Card title="アトラクション一覧" note="行を押すと上のグラフに切り替わります">
        <RideTable rides={d.rides} selected={ride.no} onSelect={select} />
      </Card>

      <Card title="データ品質" note="5分おきの取得がどれだけ揃ったか(営業時間内)">
        <QualityTable d={d} />
      </Card>
    </div>
  )
}
