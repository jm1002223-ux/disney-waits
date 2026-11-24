'use client'

import { useMemo, useState } from 'react'
import { Bar, BarChart, CartesianGrid, Line, LineChart, ReferenceLine, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts'
import { C, QSection, Status, Tile, TipBox, hm, md } from './ui'
import type { ParkData } from '../lib/types'

/** model.py の predict() と同じ式:max(0, a + b×指数) × その時刻の形(線形補間) */
function predict(m: { a: number; b: number; shape: [number, number][] }, slot: number, ci: number) {
  const base = Math.max(0, m.a + m.b * ci)
  const sh = m.shape
  if (!sh.length) return base
  if (slot <= sh[0][0]) return base * sh[0][1]
  if (slot >= sh[sh.length - 1][0]) return base * sh[sh.length - 1][1]
  const i = sh.findIndex(([s]) => s >= slot)
  const [x0, y0] = sh[i - 1], [x1, y1] = sh[i]
  return base * (y0 + (y1 - y0) * (slot - x0) / (x1 - x0))
}

function Q3({ d }: { d: ParkData }) {
  const rides = d.q3!.rides
  const keys = useMemo(() => Object.keys(rides).sort((a, b) => (rides[b].a + rides[b].b * 100) - (rides[a].a + rides[a].b * 100)), [rides])
  const [k, setK] = useState(keys[0])
  const [ci, setCi] = useState(100)
  const m = rides[k]
  const data = m.shape.map(([s]) => ({ t: s, w: Math.round(predict(m, s, ci)) }))
  const t0 = Math.floor((data[0]?.t ?? 480) / 60) * 60, t1 = Math.ceil((data.at(-1)?.t ?? 1380) / 60) * 60
  const ticks: number[] = []
  for (let t = t0; t <= t1; t += 120) ticks.push(t)
  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center gap-3">
        <select value={k} onChange={e => setK(e.target.value)} className="bg-zinc-900 border border-zinc-800 rounded-xl px-3 py-1.5 text-xs text-zinc-200 max-w-full">
          {keys.map(x => <option key={x} value={x}>{x}. {rides[x].name}</option>)}
        </select>
        <label className="flex items-center gap-2 text-xs text-zinc-400">
          混雑指数
          <input type="range" min={60} max={160} step={5} value={ci} onChange={e => setCi(Number(e.target.value))} className="accent-teal-400" />
          <span className="tabular-nums text-zinc-100 w-8">{ci}</span>
        </label>
      </div>
      <ResponsiveContainer width="100%" height={240}>
        <LineChart data={data} margin={{ top: 8, right: 12, bottom: 0, left: -16 }}>
          <CartesianGrid strokeDasharray="3 3" stroke={C.grid} vertical={false} />
          <XAxis dataKey="t" type="number" domain={[t0, t1]} ticks={ticks} tickFormatter={hm} tick={{ fontSize: 10, fill: C.axis }} tickLine={false} axisLine={{ stroke: C.grid }} />
          <YAxis tick={{ fontSize: 10, fill: C.axis }} tickLine={false} axisLine={false} unit="分" />
          <Tooltip cursor={{ stroke: '#52525b' }} content={({ active, payload }) => {
            if (!active || !payload?.length) return null
            const p = payload[0].payload as (typeof data)[number]
            return <TipBox><p className="font-semibold text-zinc-100">{hm(p.t)}〜</p><p className="text-zinc-300">予測 {p.w}分(混雑指数 {ci})</p></TipBox>
          }} />
          <Line type="monotone" dataKey="w" stroke={C.line} strokeWidth={2} dot={false} isAnimationActive={false} activeDot={{ r: 4, fill: C.line, stroke: '#0d1f17', strokeWidth: 2 }} />
        </LineChart>
      </ResponsiveContainer>
      <div className="flex flex-wrap gap-x-6 gap-y-1 text-xs text-zinc-400">
        <span>日平均 = <span className="text-zinc-100 tabular-nums">{m.a.toFixed(1)} + {m.b.toFixed(2)} × 指数</span></span>
        <span>当てはまり(R²) <span className="text-zinc-100 tabular-nums">{m.r2.toFixed(2)}</span></span>
        <span>学習した日数 <span className="text-zinc-100 tabular-nums">{m.days}日</span></span>
      </div>
      <div className="overflow-x-auto">
        <table className="w-full text-xs max-sm:[&_tr>*:nth-child(2)]:hidden max-sm:[&_tr>*:nth-child(4)]:hidden max-sm:[&_tr>*:nth-child(6)]:hidden max-sm:[&_td:not(.text-right)]:whitespace-normal max-sm:[&_th]:whitespace-normal">
          <thead className="text-zinc-500"><tr className="border-b border-zinc-800">
            {['アトラクション', '指数80の平均待ち', '指数100', '指数120', '指数+10あたり', 'R²'].map((h, i) => <th key={h} className={`py-2 px-2 font-normal ${i === 0 ? 'text-left' : 'text-right'} whitespace-nowrap`}>{h}</th>)}
          </tr></thead>
          <tbody>
            {keys.slice(0, 12).map(x => {
              const r = rides[x], at = (c: number) => Math.round(Math.max(0, r.a + r.b * c))
              return (
                <tr key={x} onClick={() => setK(x)} className={`border-b border-zinc-800/50 cursor-pointer ${x === k ? 'bg-teal-500/[0.07]' : 'hover:bg-white/[0.02]'}`}>
                  <td className="py-1.5 px-2 text-zinc-200 whitespace-nowrap">{x}. {r.name}</td>
                  <td className="py-1.5 px-2 text-right tabular-nums text-zinc-300">{at(80)}分</td>
                  <td className="py-1.5 px-2 text-right tabular-nums text-zinc-100">{at(100)}分</td>
                  <td className="py-1.5 px-2 text-right tabular-nums text-zinc-300">{at(120)}分</td>
                  <td className="py-1.5 px-2 text-right tabular-nums text-zinc-300">+{(r.b * 10).toFixed(1)}分</td>
                  <td className="py-1.5 px-2 text-right tabular-nums text-zinc-400">{r.r2.toFixed(2)}</td>
                </tr>
              )
            })}
          </tbody>
        </table>
      </div>
      {d.q3!.gbm_importance.length > 0 && (
        <div className="space-y-1.5">
          <p className="text-xs text-zinc-400">勾配ブースティングで予測に効いている条件(外すと誤差が何分増えるか)</p>
          {d.q3!.gbm_importance.map(x => {
            const max = Math.max(...d.q3!.gbm_importance.map(y => y.value), 0.01)
            return (
              <div key={x.name} className="flex items-center gap-2 text-xs">
                <span className="w-28 shrink-0 text-zinc-400 truncate">{x.name}</span>
                <span className="h-2 rounded-r" style={{ width: `${Math.max(0, x.value) / max * 60}%`, background: C.bar }} />
                <span className="tabular-nums text-zinc-200">{x.value.toFixed(2)}分</span>
              </div>
            )
          })}
        </div>
      )}
    </div>
  )
}

function Q4({ d }: { d: ParkData }) {
  const bt = d.q4?.backtest, gbm = d.q4?.gbm
  return (
    <div className="space-y-5">
      {bt && <>
        <div className="grid grid-cols-1 sm:grid-cols-3 gap-3">
          <Tile label="指数が分かっている場合(人気)" value={`±${bt.top.known.toFixed(1)}分`} sub={<Status ok={bt.top.known <= 10}>合格ライン ±10分以内</Status>} />
          <Tile label="指数を曜日の平均で仮定(人気)" value={`±${bt.top.unknown.toFixed(1)}分`} sub={<Status ok={bt.top.unknown < bt.top.naive}>指数なしより小さいこと</Status>} />
          <Tile label="指数なし・過去の平均だけ(人気)" value={`±${bt.top.naive.toFixed(1)}分`} sub="比べる基準" />
        </div>
        <p className="text-xs text-zinc-500">
          全アトラクションでは ±{bt.all.known.toFixed(1)}分 / ±{bt.all.unknown.toFixed(1)}分 / ±{bt.all.naive.toFixed(1)}分。1日ずつ隠して、残りの日で作ったモデルで予測({bt.days}日分)。
        </p>
        <div>
          <p className="text-xs text-zinc-400 mb-1">日ごとの平均誤差(指数が分かっている場合)</p>
          <ResponsiveContainer width="100%" height={170}>
            <BarChart data={bt.per_day.map(x => ({ ...x, label: md(x.date) }))} margin={{ top: 8, right: 8, bottom: 0, left: -16 }}>
              <CartesianGrid strokeDasharray="3 3" stroke={C.grid} vertical={false} />
              <XAxis dataKey="label" tick={{ fontSize: 10, fill: C.axis }} tickLine={false} axisLine={{ stroke: C.grid }} interval="preserveStartEnd" />
              <YAxis tick={{ fontSize: 10, fill: C.axis }} tickLine={false} axisLine={false} unit="分" />
              <Tooltip cursor={{ fill: 'rgba(255,255,255,0.04)' }} content={({ active, payload }) => {
                if (!active || !payload?.length) return null
                const p = payload[0].payload as (typeof bt.per_day)[number] & { label: string }
                return <TipBox><p className="font-semibold text-zinc-100">{p.label}</p><p className="text-zinc-300">平均誤差 ±{p.err}分</p><p className="text-zinc-500">実際の指数 {p.ci_true ?? '-'} / 曜日から仮定 {p.ci_guess}</p></TipBox>
              }} />
              <Bar dataKey="err" fill={C.bar} radius={[4, 4, 0, 0]} maxBarSize={22} />
            </BarChart>
          </ResponsiveContainer>
        </div>
      </>}
      {gbm && (
        <div>
          <p className="text-xs text-zinc-400 mb-1">5つの方式の比較(人気アトラクションの平均誤差、日単位の交差検証、gbm.py)</p>
          <ResponsiveContainer width="100%" height={200}>
            <BarChart data={gbm} layout="vertical" margin={{ top: 4, right: 24, bottom: 0, left: 8 }}>
              <CartesianGrid strokeDasharray="3 3" stroke={C.grid} horizontal={false} />
              <XAxis type="number" tick={{ fontSize: 10, fill: C.axis }} tickLine={false} axisLine={{ stroke: C.grid }} unit="分" />
              <YAxis type="category" dataKey="method" width={150} tick={{ fontSize: 10, fill: '#d4d4d8' }} tickLine={false} axisLine={false} />
              <ReferenceLine x={10} stroke={C.ref} strokeDasharray="4 4" label={{ value: '±10分', position: 'top', fill: C.ref, fontSize: 10 }} />
              <Tooltip cursor={{ fill: 'rgba(255,255,255,0.04)' }} content={({ active, payload }) => {
                if (!active || !payload?.length) return null
                const p = payload[0].payload as (typeof gbm)[number]
                return <TipBox><p className="font-semibold text-zinc-100">{p.method}</p><p className="text-zinc-300">人気 ±{p.top ?? '-'}分 / 全体 ±{p.all}分</p></TipBox>
              }} />
              <Bar dataKey="top" fill={C.bar} radius={[0, 4, 4, 0]} maxBarSize={18} />
            </BarChart>
          </ResponsiveContainer>
        </div>
      )}
      {bt && (
        <div className="overflow-x-auto">
          <p className="text-xs text-zinc-400 mb-1">外れやすいアトラクション(上位10)</p>
          <table className="w-full text-xs max-sm:[&_tr>*:nth-child(5)]:hidden max-sm:[&_td:not(.text-right)]:whitespace-normal max-sm:[&_th]:whitespace-normal">
            <thead className="text-zinc-500"><tr className="border-b border-zinc-800">
              {['アトラクション', '指数が分かっている', '曜日の平均で仮定', '指数なし', '比較した数'].map((h, i) => <th key={h} className={`py-2 px-2 font-normal ${i === 0 ? 'text-left' : 'text-right'} whitespace-nowrap`}>{h}</th>)}
            </tr></thead>
            <tbody>
              {bt.rides.slice(0, 10).map(r => (
                <tr key={r.no} className="border-b border-zinc-800/50">
                  <td className="py-1.5 px-2 text-zinc-200 whitespace-nowrap">{r.no}. {r.name}</td>
                  <td className="py-1.5 px-2 text-right tabular-nums text-zinc-100">±{r.known}分</td>
                  <td className="py-1.5 px-2 text-right tabular-nums text-zinc-300">±{r.unknown}分</td>
                  <td className="py-1.5 px-2 text-right tabular-nums text-zinc-300">±{r.naive}分</td>
                  <td className="py-1.5 px-2 text-right tabular-nums text-zinc-500">{r.n}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  )
}

function Q5({ d }: { d: ParkData }) {
  const q = d.q5!
  return (
    <div className="space-y-4">
      <div className="grid grid-cols-1 sm:grid-cols-3 gap-3">
        <Tile label="グループ数" value={q.k} sub="シルエット係数が最大になる数" />
        <Tile label="シルエット係数" value={q.silhouette.toFixed(2)} sub={<Status ok={q.silhouette >= 0.25}>合格ライン 0.25以上</Status>} />
        <Tile label="安定性(ブートストラップARI)" value={q.ari.toFixed(2)} sub={<Status ok={q.ari >= 0.75}>合格ライン 0.75以上</Status>} />
      </div>
      {q.ari < 0.75 && <p className="text-xs text-amber-200">安定性が合格ラインに届いていないので、データが増えるまで参考扱いにします(計画書)。</p>}
      <div className="grid md:grid-cols-2 gap-3">
        {q.groups.map(g => (
          <div key={g.id} className="min-w-0 rounded-xl border border-zinc-800 bg-zinc-900/40 p-3 space-y-2">
            <p className="text-xs"><span className="text-teal-300 font-semibold">グループ{g.id}</span><span className="text-zinc-400 ml-2">{g.name}</span></p>
            <ul className="text-xs space-y-0.5">
              {g.members.map(m => (
                <li key={m.no} className="flex justify-between gap-2">
                  <span className="text-zinc-200 truncate">{m.no}. {m.name}</span>
                  <span className="text-zinc-500 tabular-nums whitespace-nowrap">平均{Math.round(m.mean)}分・確からしさ {m.confidence ?? '-'}</span>
                </li>
              ))}
            </ul>
          </div>
        ))}
      </div>
    </div>
  )
}

/* ── タブ③ 予測と分類(12/14):Q3・Q4・Q5 ── */
export function TabModel({ d }: { d: ParkData }) {
  const miss = (cmd: string) => <>出力がありません。<code className="text-teal-300">{cmd}</code> を実行してください</>
  return (
    <div className="space-y-6">
      <QSection q="Q3" title="混雑指数Xの日、Y時の待ち時間は何分か" method="混雑指数モデル(日平均 = a + b×指数、×時間帯の形)と勾配ブースティングを比較" source="model.py / gbm.py / ノート④"
        minDays={10} first="12/14" dataDays={d.data_days} ready={!!d.q3} missing={miss(`python model.py --park ${d.park}`)} calc={d.outputs.model}>
        {d.q3 && <Q3 d={d} />}
      </QSection>
      <QSection q="Q4" title="Q3の予測はどれくらい当たるか" method="学習に使わない日で採点し、過去の平均を基準に5方式を比較" source="model.py --backtest / gbm.py"
        minDays={10} first="12/14" dataDays={d.data_days} ready={!!(d.q4?.backtest || d.q4?.gbm)} missing={miss(`python model.py --park ${d.park} --backtest`)} calc={d.outputs.backtest}>
        <Q4 d={d} />
      </QSection>
      <QSection q="Q5" title="似た傾向のアトラクションはどれか" method="k-means++ + シルエット係数 + ブートストラップ" source="insights.py"
        minDays={14} first="12/14" dataDays={d.data_days} ready={!!d.q5} missing={miss(`python insights.py --park ${d.park}`)} calc={d.outputs.insights}>
        {d.q5 && <Q5 d={d} />}
      </QSection>
    </div>
  )
}
