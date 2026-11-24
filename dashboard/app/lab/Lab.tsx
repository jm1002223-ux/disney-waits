'use client'

import { useMemo, useState } from 'react'
import { CartesianGrid, Line, LineChart, ReferenceArea, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts'
import { C, Segmented, TipBox, hm } from '../components/ui'
import type { ParkData, Ride } from '../lib/types'

/* Q1「いつ何に乗れば空いているか」の見せ方を3通り並べて比べる試作 */

type Pt = { t: number; med: number }
const QUIET = 0.8 // その日の平均の8割以下を「狙い目」とする(試作の仮の基準)
const STEP = 15

const OPEN_FROM = 6 * 60 // 6時より前は閉園後の名残り(0時台に閉園前の値が残る)なので使わない
const points = (r: Ride): Pt[] =>
  (r.profile.all ?? []).filter(s => s[1] != null && s[0] >= OPEN_FROM).map(([t, m]) => ({ t, med: m as number }))

/** 折れ線用:データの抜けている所に null を挟んで、線をつなげない */
const withGaps = (pts: Pt[]) => pts.flatMap((p, k) =>
  k > 0 && p.t - pts[k - 1].t > STEP ? [{ t: pts[k - 1].t + STEP, med: null }, p] : [p])

function avgOf(pts: Pt[]) {
  return pts.length ? pts.reduce((a, p) => a + p.med, 0) / pts.length : null
}

/** 狙い目の時間帯(連続する15分枠をまとめる) */
function quietWindows(pts: Pt[], avg: number) {
  const out: { from: number; to: number; min: number }[] = []
  for (const p of pts) {
    if (p.med > avg * QUIET) continue
    const last = out.at(-1)
    if (last && p.t - last.to <= 0) { last.to = p.t + STEP; last.min = Math.min(last.min, p.med) }
    else out.push({ from: p.t, to: p.t + STEP, min: p.med })
  }
  return out.filter(w => w.to - w.from >= 30) // 15分だけの細切れは外す
}

type Info = { ride: Ride; pts: Pt[]; avg: number; wins: ReturnType<typeof quietWindows>; best: Pt }

function useInfos(d: ParkData, n: number): Info[] {
  return useMemo(() => d.rides
    .map(ride => {
      const pts = points(ride), avg = avgOf(pts)
      if (!pts.length || avg == null || avg < 10) return null // 待ちがほぼない施設は除く
      const best = pts.reduce((a, p) => (p.med < a.med ? p : a))
      return { ride, pts, avg, wins: quietWindows(pts, avg), best }
    })
    .filter((x): x is Info => x !== null)
    .sort((a, b) => b.avg - a.avg)
    .slice(0, n), [d, n])
}

const winText = (w: { from: number; to: number }) => `${hm(w.from)}〜${hm(w.to)}`

/* ── 共通:結論の一言 ── */
function Headline({ infos }: { infos: Info[] }) {
  return (
    <ul className="space-y-1 text-sm text-zinc-200">
      {infos.slice(0, 3).map(i => {
        const w = [...i.wins].sort((a, b) => a.min - b.min)[0]
        return (
          <li key={i.ride.no}>
            <span className="font-semibold text-white">{i.ride.name}</span>:
            {w ? <>{winText(w)} が狙い目(いつもは平均{Math.round(i.avg)}分 → <span className="text-teal-300 font-semibold">{Math.round(w.min)}分</span>)</> : <>はっきり空く時間帯なし(平均{Math.round(i.avg)}分)</>}
          </li>
        )
      })}
    </ul>
  )
}

/* ── 案A:小さな折れ線をたくさん並べる ── */
function OptionA({ infos, t0, t1, ymax }: { infos: Info[]; t0: number; t1: number; ymax: number }) {
  const ticks: number[] = []
  for (let t = Math.ceil(t0 / 180) * 180; t <= t1; t += 180) ticks.push(t)
  return (
    <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
      {infos.map(i => (
        <div key={i.ride.no} className="min-w-0 rounded-xl border border-zinc-800/80 bg-zinc-900/60 p-3">
          <div className="flex items-baseline justify-between gap-2">
            <p className="truncate text-xs font-semibold text-zinc-100">{i.ride.name}</p>
            <p className="shrink-0 text-[11px] text-zinc-500">平均 {Math.round(i.avg)}分</p>
          </div>
          <p className="mt-0.5 text-[11px] text-zinc-400">
            狙い目 <span className="text-teal-300">{i.wins.length ? i.wins.map(winText).join('、') : 'なし'}</span>
          </p>
          <div className="h-24">
            <ResponsiveContainer width="100%" height="100%">
              <LineChart data={withGaps(i.pts)} margin={{ top: 6, right: 4, bottom: 0, left: 0 }}>
                <CartesianGrid stroke={C.grid} vertical={false} strokeDasharray="3 3" />
                {i.wins.map(w => <ReferenceArea key={w.from} x1={w.from} x2={w.to} fill={C.band} stroke="none" ifOverflow="hidden" />)}
                <XAxis dataKey="t" type="number" domain={[t0, t1]} ticks={ticks} tickFormatter={hm} tick={{ fontSize: 9, fill: C.axis }} tickLine={false} axisLine={false} />
                <YAxis domain={[0, ymax]} ticks={[0, ymax / 2, ymax]} tick={{ fontSize: 9, fill: C.axis }} tickLine={false} axisLine={false} width={24} />
                <Tooltip cursor={{ stroke: '#52525b' }} content={({ active, payload }) => {
                  if (!active || !payload?.length) return null
                  const p = payload[0].payload as { t: number; med: number | null }
                  if (p.med == null) return null
                  return <TipBox><p className="text-zinc-100">{hm(p.t)}〜 <span className="font-semibold">{Math.round(p.med)}分</span></p></TipBox>
                }} />
                <Line dataKey="med" stroke={C.line} strokeWidth={2} dot={false} isAnimationActive={false} connectNulls={false} />
              </LineChart>
            </ResponsiveContainer>
          </div>
        </div>
      ))}
    </div>
  )
}

/* ── 案B:狙い目の時間帯だけを横の帯で並べる(時刻表のような形) ── */
function OptionB({ infos, t0, t1 }: { infos: Info[]; t0: number; t1: number }) {
  const [hover, setHover] = useState<string | null>(null)
  const span = t1 - t0
  const x = (t: number) => `${((t - t0) / span) * 100}%`
  const hours: number[] = []
  for (let t = Math.ceil(t0 / 60) * 60; t <= t1; t += 60) hours.push(t)
  return (
    <div className="space-y-2">
      <p className="min-h-4 text-xs text-zinc-400">{hover ?? '帯にカーソルを合わせると詳細'}</p>
      <div className="overflow-x-auto">
        <div className="min-w-[560px] space-y-1.5 pr-3">
          <div className="flex">
            <div className="w-44 shrink-0" />
            <div className="relative h-4 flex-1">
              {hours.map(h => (
                <span key={h} className="absolute -translate-x-1/2 text-[10px] text-zinc-500" style={{ left: x(h) }}>{h / 60}</span>
              ))}
            </div>
          </div>
          {infos.map(i => {
            const first = i.pts[0].t, last = i.pts.at(-1)!.t + STEP
            return (
              <div key={i.ride.no} className="flex items-center">
                <div className="w-44 shrink-0 truncate pr-2 text-xs text-zinc-300">{i.ride.name}</div>
                <div className="relative h-5 flex-1">
                  {hours.map(h => <span key={h} className="absolute inset-y-0 w-px bg-zinc-800/70" style={{ left: x(h) }} />)}
                  {/* データのある時間帯 */}
                  <span className="absolute top-1/2 h-px -translate-y-1/2 bg-zinc-600" style={{ left: x(first), width: `calc(${x(last)} - ${x(first)})` }} />
                  {i.wins.map(w => (
                    <span key={w.from}
                      onMouseEnter={() => setHover(`${i.ride.name}:${winText(w)} 最短 ${Math.round(w.min)}分(平均 ${Math.round(i.avg)}分)`)}
                      onMouseLeave={() => setHover(null)}
                      className="absolute inset-y-0.5 flex items-center justify-center rounded text-[10px] font-semibold text-zinc-950"
                      style={{ left: x(w.from), width: `calc(${x(w.to)} - ${x(w.from)} - 2px)`, background: C.line }}>
                      {w.to - w.from >= 45 ? `${Math.round(w.min)}分` : ''}
                    </span>
                  ))}
                </div>
              </div>
            )
          })}
        </div>
      </div>
      <div className="flex flex-wrap gap-4 text-[11px] text-zinc-500">
        <span className="inline-flex items-center gap-1.5"><span className="h-2.5 w-5 rounded" style={{ background: C.line }} />狙い目(平均の8割以下)。数字はその間の最短</span>
        <span className="inline-flex items-center gap-1.5"><span className="h-px w-5 bg-zinc-600" />データのある時間帯</span>
      </div>
    </div>
  )
}

/* ── 案C:時刻を選ぶと、その時刻に空いている順に並ぶ ── */
function OptionC({ infos, t0, t1 }: { infos: Info[]; t0: number; t1: number }) {
  const [t, setT] = useState(() => Math.min(Math.max(14 * 60, t0), t1 - STEP))
  const rows = infos
    .map(i => {
      const p = i.pts.find(p => p.t === t)
      return p ? { i, med: p.med, diff: p.med - i.avg } : null
    })
    .filter((r): r is NonNullable<typeof r> => r !== null)
    .sort((a, b) => a.med - b.med)
  const max = Math.max(...infos.map(i => Math.max(...i.pts.map(p => p.med))), 1)
  return (
    <div className="space-y-3">
      <div className="flex flex-wrap items-center gap-3">
        <span className="text-2xl font-bold tabular-nums text-white">{hm(t)}</span>
        <input type="range" min={t0} max={t1 - STEP} step={STEP} value={t} onChange={e => setT(Number(e.target.value))}
          className="flex-1 min-w-40 accent-teal-400" aria-label="時刻" />
      </div>
      {rows.length ? (
        <div className="space-y-1.5">
          {rows.map(({ i, med, diff }) => (
            <div key={i.ride.no} className="flex items-center gap-2 text-xs">
              <div className="w-44 shrink-0 truncate text-zinc-300">{i.ride.name}</div>
              <div className="relative h-4 flex-1">
                <span className="absolute inset-y-0 left-0 rounded-r" style={{ width: `${(med / max) * 100}%`, background: C.bar }} />
                {/* いつもの平均の位置 */}
                <span className="absolute -inset-y-0.5 w-0.5 bg-zinc-300" style={{ left: `${(i.avg / max) * 100}%` }} title={`平均 ${Math.round(i.avg)}分`} />
              </div>
              <div className="w-12 shrink-0 text-right tabular-nums text-zinc-100">{Math.round(med)}分</div>
              <div className={`w-16 shrink-0 text-right tabular-nums ${diff <= 0 ? 'text-teal-300' : 'text-zinc-500'}`}>
                {diff <= 0 ? `${Math.round(diff)}分` : `+${Math.round(diff)}分`}
              </div>
            </div>
          ))}
        </div>
      ) : <p className="text-xs text-zinc-500">この時刻のデータはまだありません。</p>}
      <div className="flex flex-wrap gap-4 text-[11px] text-zinc-500">
        <span className="inline-flex items-center gap-1.5"><span className="h-2.5 w-5 rounded" style={{ background: C.bar }} />この時刻の待ち時間(中央値)</span>
        <span className="inline-flex items-center gap-1.5"><span className="h-3 w-0.5 bg-zinc-300" />いつもの平均</span>
        <span>右端:平均との差(マイナス=いつもより空いている)</span>
      </div>
    </div>
  )
}

function Option({ id, title, question, good, bad, children }: { id: string; title: string; question: string; good: string; bad: string; children: React.ReactNode }) {
  return (
    <section className="min-w-0 space-y-4 rounded-2xl border border-zinc-800/70 bg-zinc-900/50 p-4 sm:p-5">
      <div className="space-y-1">
        <h2 className="text-base font-semibold text-white"><span className="mr-2 text-teal-300">案{id}</span>{title}</h2>
        <p className="text-xs text-zinc-400">答える問い:{question}</p>
        <p className="text-xs text-zinc-500">向いている:{good} / 弱い:{bad}</p>
      </div>
      {children}
    </section>
  )
}

export function Lab({ parks }: { parks: ParkData[] }) {
  const [code, setCode] = useState(parks[0].park)
  const d = parks.find(p => p.park === code) ?? parks[0]
  const infos = useInfos(d, 12)
  const all = infos.flatMap(i => i.pts)
  const t0 = all.length ? Math.floor(Math.min(...all.map(p => p.t)) / 60) * 60 : 480
  const t1 = all.length ? Math.ceil((Math.max(...all.map(p => p.t)) + STEP) / 60) * 60 : 1440
  const ymax = Math.ceil(Math.max(10, ...all.map(p => p.med)) / 10) * 10

  return (
    <div className="space-y-6">
      <div className="space-y-3">
        <div className="flex flex-wrap items-center justify-between gap-3">
          <h1 className="text-lg font-bold text-white">Q1 の見せ方の比較(試作)</h1>
          <Segmented value={code} options={parks.map(p => [p.park, p.park] as [string, string])} onChange={setCode} />
        </div>
        <p className="rounded-lg border border-amber-500/30 bg-amber-500/10 px-3 py-1.5 text-xs text-amber-200">
          データ {d.data_days}日分の参考値です。11/23の朝(7〜12時)は取れていないので、朝の狙い目はまだ出ません。待ち時間の多い上位{infos.length}施設を表示。
        </p>
        <div className="rounded-2xl border border-teal-500/20 bg-teal-500/5 p-4">
          <p className="mb-2 text-xs text-teal-300">共通:一番上に出す「分かったこと」(自動で作る)</p>
          <Headline infos={infos} />
        </div>
      </div>

      <Option id="A" title="小さな折れ線を並べる" question="各アトラクションは1日の中でどう混み、どこで空くか"
        good="形の違いが一目で比べられる。網掛けが狙い目" bad="施設が多いと縦に長くなる">
        <OptionA infos={infos} t0={t0} t1={t1} ymax={ymax} />
      </Option>

      <Option id="B" title="狙い目の時間帯だけを帯で示す" question="何時にどれへ行けばいいか(1日の予定を立てる)"
        good="予定表に直結。読む量が最小" bad="何分待つかの細かさは捨てている">
        <OptionB infos={infos} t0={t0} t1={t1} />
      </Option>

      <Option id="C" title="時刻を選ぶと空いている順に並ぶ" question="いま(その時刻)なら何に乗るのがいいか"
        good="当日の判断にそのまま使える" bad="1日全体の流れは見えない">
        <OptionC infos={infos} t0={t0} t1={t1} />
      </Option>
    </div>
  )
}
