'use client'

import { useMemo, useState } from 'react'
import { Area, Bar, BarChart, CartesianGrid, ComposedChart, Line, ReferenceLine, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts'
import { C, QSection, RAMP, Segmented, TipBox, hm, md, mins, pct, rampColor } from './ui'
import type { ParkData, Ride } from '../lib/types'

type Kind = 'all' | 'weekday' | 'weekend'
const KIND_LABEL: Record<Kind, string> = { all: '全日', weekday: '平日', weekend: '週末' }
const HEAT_CUTS = [10, 20, 30, 45, 60, 90, 120]

/* ── Q1 時間帯ごとの待ち時間 ── */
function ProfileChart({ ride, kind }: { ride: Ride; kind: Kind }) {
  const data = (ride.profile[kind] ?? []).map(([t, med, p90]) => ({ t, med, p90, band: med != null && p90 != null ? [med, p90] : null }))
  if (data.length < 2) return <p className="text-xs text-zinc-500">この条件のデータがまだありません。</p>
  const t0 = Math.floor(data[0].t / 60) * 60, t1 = Math.ceil(data[data.length - 1].t / 60) * 60
  const ticks: number[] = []
  for (let t = t0; t <= t1; t += 120) ticks.push(t)
  return (
    <ResponsiveContainer width="100%" height={260}>
      <ComposedChart data={data} margin={{ top: 8, right: 12, bottom: 0, left: -16 }}>
        <CartesianGrid strokeDasharray="3 3" stroke={C.grid} vertical={false} />
        <XAxis dataKey="t" type="number" domain={[t0, t1]} ticks={ticks} tickFormatter={hm} tick={{ fontSize: 10, fill: C.axis }} tickLine={false} axisLine={{ stroke: C.grid }} />
        <YAxis tick={{ fontSize: 10, fill: C.axis }} tickLine={false} axisLine={false} unit="分" />
        <Tooltip cursor={{ stroke: '#52525b', strokeWidth: 1 }} content={({ active, payload }) => {
          if (!active || !payload?.length) return null
          const p = payload[0].payload as (typeof data)[number]
          return <TipBox><p className="font-semibold text-zinc-100">{hm(p.t)}〜</p><p className="text-zinc-300">中央値 {p.med ?? '-'}分</p><p className="text-zinc-500">90%点 {p.p90 ?? '-'}分(10回に1回はこれ以上)</p></TipBox>
        }} />
        <Area type="monotone" dataKey="band" stroke="none" fill={C.band} isAnimationActive={false} activeDot={false} />
        <Line type="monotone" dataKey="med" stroke={C.line} strokeWidth={2} dot={false} activeDot={{ r: 4, fill: C.line, stroke: '#0d1f17', strokeWidth: 2 }} isAnimationActive={false} />
      </ComposedChart>
    </ResponsiveContainer>
  )
}

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
        <Legend cuts={HEAT_CUTS} unit="分" />
      </div>
      <div className="overflow-x-auto">
        <table className="text-xs border-separate" style={{ borderSpacing: 2 }}>
          <thead><tr><th className="sticky left-0 bg-[#141f1b] z-10" />{hours.map(h => <th key={h} className="font-normal text-zinc-500 w-7 text-center">{h}</th>)}</tr></thead>
          <tbody>
            {rides.map(r => {
              const byH = new Map(r.hourly), sel = r.no === selected
              return (
                <tr key={r.no} onClick={() => onSelect(r.no)} className="cursor-pointer group">
                  <td className={`sticky left-0 z-10 bg-[#141f1b] pr-3 py-0.5 whitespace-nowrap max-w-[8.5rem] sm:max-w-56 truncate ${sel ? 'text-teal-300 font-semibold' : 'text-zinc-400 group-hover:text-zinc-200'}`}>{r.no}. {r.name}</td>
                  {hours.map(h => {
                    const v = byH.get(h)
                    return <td key={h} className="w-7 h-5 rounded-[4px]" style={{ background: rampColor(v, HEAT_CUTS), outline: sel ? '1px solid rgba(45,212,191,0.35)' : undefined }}
                      onMouseEnter={() => setHover({ name: r.name, h, v: v ?? null })} onMouseLeave={() => setHover(null)} />
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

export function Legend({ cuts, unit, low = '少ない', high = '多い' }: { cuts: number[]; unit: string; low?: string; high?: string }) {
  return (
    <div className="flex items-center gap-1 text-xs text-zinc-500">
      <span>{low}</span>
      {RAMP.slice(1).map((c, i) => <span key={c} className="w-4 h-3 rounded-sm" style={{ background: c }} title={`${cuts[i]}${unit}〜`} />)}
      <span>{high}({unit})</span>
    </div>
  )
}

/* ── Q2 混雑指数 ── */
type Variant = 'all' | 'ex_thanksgiving' | 'ex_christmas' | 'ex_both'
export function CrowdIndex({ d, variants }: { d: ParkData; variants: Variant[] }) {
  const [v, setV] = useState<Variant>('all')
  const ci = d.crowd_index?.[v]
  const label: Record<Variant, string> = {
    all: '全期間を基準', ex_thanksgiving: `${d.special.thanksgiving?.label}を除いて基準`, ex_christmas: `${d.special.christmas?.label}を除いて基準`, ex_both: '両方を除いて基準',
  }
  if (!ci) return <p className="text-xs text-zinc-500">混雑指数がまだありません。</p>
  const shown = variants.filter(k => d.crowd_index?.[k])   // 東京は感謝祭がないので、ない比べ方は出さない
  const data = d.days.filter(x => ci[x.date] != null).map(x => {
    const sp = Object.values(d.special).find(s => x.date >= s.from && x.date <= s.to)
    return { label: `${md(x.date)}${x.weekday}`, ci: ci[x.date], holiday: x.holiday, sp: sp?.label, open: x.open, close: x.close }
  })
  return (
    <div className="space-y-3">
      {shown.length > 1 && <Segmented value={v} options={shown.map(k => [k, label[k]] as [Variant, string])} onChange={setV} />}
      <ResponsiveContainer width="100%" height={220}>
        <BarChart data={data} margin={{ top: 8, right: 8, bottom: 0, left: -16 }}>
          <CartesianGrid strokeDasharray="3 3" stroke={C.grid} vertical={false} />
          <XAxis dataKey="label" tick={{ fontSize: 10, fill: C.axis }} tickLine={false} axisLine={{ stroke: C.grid }} interval="preserveStartEnd" />
          <YAxis tick={{ fontSize: 10, fill: C.axis }} tickLine={false} axisLine={false} />
          <ReferenceLine y={100} stroke={C.ref} strokeDasharray="4 4" label={{ value: '基準 100', position: 'insideTopRight', fill: C.ref, fontSize: 10 }} />
          <Tooltip cursor={{ fill: 'rgba(255,255,255,0.04)' }} content={({ active, payload }) => {
            if (!active || !payload?.length) return null
            const p = payload[0].payload as (typeof data)[number]
            return <TipBox><p className="font-semibold text-zinc-100">{p.label}{p.holiday ? `・${p.holiday}` : ''}</p><p className="text-zinc-300">混雑指数 {p.ci}</p>{p.sp && <p className="text-zinc-500">{p.sp}</p>}<p className="text-zinc-500">営業(推定){p.open}〜{p.close}</p></TipBox>
          }} />
          <Bar dataKey="ci" fill={C.bar} radius={[4, 4, 0, 0]} maxBarSize={24} />
        </BarChart>
      </ResponsiveContainer>
      <p className="text-xs text-zinc-500">100 = 基準にした期間の平均的な日。特殊な日を基準に含めると、ほかの日の指数が低めに出ます(計画書:含める場合と除く場合を比べる)。</p>
    </div>
  )
}

/* ── タブ② 基礎分析(12/7):Q1・Q2・Q6・Q7 ── */
export function TabBasic({ d }: { d: ParkData }) {
  const [rideNo, setRideNo] = useState(d.rides[0]?.no)
  const [kind, setKind] = useState<Kind>('all')
  const ride = d.rides.find(r => r.no === rideNo) ?? d.rides[0]
  const ins = d.outputs.insights
  const insMissing = <>出力がありません。<code className="text-teal-300">python insights.py --park {d.park}</code> を実行してください</>
  const avgOf = (k: Kind) => {
    const s = ride?.profile[k]?.filter(x => x[1] != null) ?? []
    return s.length ? s.reduce((a, x) => a + (x[1] ?? 0), 0) / s.length : null
  }
  const hours = d.q7 ? Array.from(new Set(d.q7.flatMap(r => Object.keys(r.p_hour).map(Number)))).sort((a, b) => a - b) : []
  const P_CUTS = [0.02, 0.05, 0.1, 0.15, 0.2, 0.3, 0.4]

  return (
    <div className="space-y-6">
      <QSection q="Q1" title="各アトラクションは何時が空き、何時が混むか" method="15分ごとの中央値・90%点(平日と週末の差も)" source="analyze.py / ノート②③"
        minDays={5} first="12/7" dataDays={d.data_days} ready={!!ride}>
        {ride && <>
          <div className="flex flex-wrap items-center gap-2">
            <select value={ride.no} onChange={e => setRideNo(Number(e.target.value))} className="bg-zinc-900 border border-zinc-800 rounded-xl px-3 py-1.5 text-xs text-zinc-200 max-w-full">
              {d.rides.map(r => <option key={r.no} value={r.no}>{r.no}. {r.name}</option>)}
            </select>
            <Segmented value={kind} options={(Object.keys(KIND_LABEL) as Kind[]).map(k => [k, KIND_LABEL[k]])} onChange={setKind} />
          </div>
          <ProfileChart ride={ride} kind={kind} />
          <div className="flex flex-wrap gap-x-6 gap-y-1 text-xs text-zinc-400">
            <span>空く時刻 <span className="text-zinc-100">{ride.best ? `${ride.best.time}(${Math.round(ride.best.wait)}分)` : '-'}</span></span>
            <span>ピーク <span className="text-zinc-100">{ride.peak ? `${ride.peak.time}(${Math.round(ride.peak.wait)}分)` : '-'}</span></span>
            <span>平日の平均 <span className="text-zinc-100">{mins(avgOf('weekday'))}</span></span>
            <span>週末の平均 <span className="text-zinc-100">{mins(avgOf('weekend'))}</span></span>
          </div>
          <div className="pt-2 border-t border-zinc-800/60">
            <Heatmap rides={d.rides} selected={ride.no} onSelect={setRideNo} />
          </div>
        </>}
      </QSection>

      <QSection q="Q2" title="その日がどれくらい混んでいたか(混雑指数)" method="人気アトラクションの日平均 ÷ 期間平均 × 100(model.py と同じ計算)" source="model.py / ノート①"
        minDays={3} first="12/7" dataDays={d.data_days} ready={!!d.crowd_index}>
        <CrowdIndex d={d} variants={['all', 'ex_thanksgiving']} />
      </QSection>

      <QSection q="Q6" title="朝いちばんに乗るべき順番は" method="(昼11〜17時の待ち − 開園30分の待ち)× 開園時の稼働率" source="insights.py / ノート⑨"
        minDays={7} first="12/7" dataDays={d.data_days} ready={!!d.q6} missing={insMissing} calc={ins}>
        {d.q6 && (
          <div className="overflow-x-auto">
            <table className="w-full text-xs max-sm:[&_tr>*:nth-child(3)]:hidden max-sm:[&_tr>*:nth-child(5)]:hidden max-sm:[&_tr>*:nth-child(6)]:hidden max-sm:[&_td:not(.text-right)]:whitespace-normal max-sm:[&_th]:whitespace-normal">
              <thead className="text-zinc-500"><tr className="border-b border-zinc-800">
                {['順位', 'アトラクション', 'グループ', '開園30分', '11〜17時', '開園時に動いている確率', '朝に乗ると得する時間'].map((h, i) => <th key={h} className={`py-2 px-2 font-normal ${i === 1 ? 'text-left' : 'text-right'} whitespace-nowrap`}>{h}</th>)}
              </tr></thead>
              <tbody>
                {d.q6.slice(0, 15).map(r => {
                  const max = Math.max(...d.q6!.map(x => x.saved), 1)
                  return (
                    <tr key={r.no} className="border-b border-zinc-800/50">
                      <td className="py-1.5 px-2 text-right tabular-nums text-zinc-400">{r.rank}</td>
                      <td className="py-1.5 px-2 text-zinc-200 whitespace-nowrap">{r.no}. {r.name}</td>
                      <td className="py-1.5 px-2 text-right text-zinc-400">{r.group}</td>
                      <td className="py-1.5 px-2 text-right tabular-nums text-zinc-300">{mins(r.early)}</td>
                      <td className="py-1.5 px-2 text-right tabular-nums text-zinc-300">{mins(r.mid)}</td>
                      <td className="py-1.5 px-2 text-right tabular-nums text-zinc-300">{pct(r.p_open)}</td>
                      <td className="py-1.5 px-2 text-right whitespace-nowrap">
                        <span className="inline-block h-2 rounded-r align-middle mr-2" style={{ width: `${Math.max(0, r.saved) / max * 80}px`, background: C.bar }} />
                        <span className="tabular-nums text-zinc-100">{mins(r.saved)}</span>
                      </td>
                    </tr>
                  )
                })}
              </tbody>
            </table>
          </div>
        )}
      </QSection>

      <QSection q="Q7" title="シス調はどれくらい、何時に起きるか" method="営業中の停止区間の集計(5分未満の停止は数え落とす)" source="insights.py / ノート⑥"
        minDays={7} first="12/7" dataDays={d.data_days} ready={!!d.q7} missing={insMissing} calc={ins}>
        {d.q7 && <>
          <div className="overflow-x-auto">
            <table className="w-full text-xs max-sm:[&_tr>*:nth-child(3)]:hidden max-sm:[&_tr>*:nth-child(5)]:hidden max-sm:[&_tr>*:nth-child(6)]:hidden max-sm:[&_td:not(.text-right)]:whitespace-normal max-sm:[&_th]:whitespace-normal">
              <thead className="text-zinc-500"><tr className="border-b border-zinc-800">
                {['アトラクション', '1日に1回以上止まる確率', '1日あたりの回数', '平均の停止時間', '開園時に動いていない確率', '止まり始めが多い時間帯'].map((h, i) => <th key={h} className={`py-2 px-2 font-normal ${i === 0 ? 'text-left' : 'text-right'} whitespace-nowrap`}>{h}</th>)}
              </tr></thead>
              <tbody>
                {d.q7.slice(0, 15).map(r => (
                  <tr key={r.no} className="border-b border-zinc-800/50">
                    <td className="py-1.5 px-2 text-zinc-200 whitespace-nowrap">{r.no}. {r.name}</td>
                    <td className="py-1.5 px-2 text-right tabular-nums text-zinc-100">{pct(r.p_day)}</td>
                    <td className="py-1.5 px-2 text-right tabular-nums text-zinc-300">{r.events_per_day.toFixed(2)}回</td>
                    <td className="py-1.5 px-2 text-right tabular-nums text-zinc-300">{mins(r.avg_min)}</td>
                    <td className="py-1.5 px-2 text-right tabular-nums text-zinc-300">{pct(r.p_morning_down)}</td>
                    <td className="py-1.5 px-2 text-right text-zinc-400 whitespace-nowrap">
                      {Object.entries(r.start_hours).sort((a, b) => b[1] - a[1]).slice(0, 3).map(([h]) => `${h}時台`).join('、') || '-'}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <div className="pt-2 border-t border-zinc-800/60 space-y-2">
            <div className="flex flex-wrap items-center justify-between gap-2 text-xs text-zinc-400">
              <span>時間帯ごとの「止まっている確率」(上位15件)</span>
              <Legend cuts={P_CUTS.map(x => x * 100)} unit="%" low="低い" high="高い" />
            </div>
            <div className="overflow-x-auto">
              <table className="text-xs border-separate" style={{ borderSpacing: 2 }}>
                <thead><tr><th className="sticky left-0 bg-[#141f1b] z-10" />{hours.map(h => <th key={h} className="font-normal text-zinc-500 w-7 text-center">{h}</th>)}</tr></thead>
                <tbody>
                  {d.q7.slice(0, 15).map(r => (
                    <tr key={r.no}>
                      <td className="sticky left-0 z-10 bg-[#141f1b] pr-3 py-0.5 whitespace-nowrap max-w-[8.5rem] sm:max-w-56 truncate text-zinc-400">{r.no}. {r.name}</td>
                      {hours.map(h => {
                        const p = r.p_hour[String(h)]
                        return <td key={h} className="w-7 h-5 rounded-[4px]" style={{ background: rampColor(p, P_CUTS) }} title={`${r.name}・${h}時台:${pct(p)}`} />
                      })}
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
        </>}
      </QSection>
    </div>
  )
}
