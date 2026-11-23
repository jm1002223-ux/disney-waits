'use client'

import { AlertTriangle, CheckCircle2, CircleDashed, Clock } from 'lucide-react'

// 色:ティール1色を軸にする(系列は常に1つずつ表示するので、分類色は使わない)
export const C = {
  line: '#2dd4bf',          // teal-400
  band: 'rgba(45,212,191,0.16)',
  bar: '#14b8a6',           // teal-500
  grid: '#27272a',
  axis: '#71717a',
  ref: '#a1a1aa',
  good: '#0ca30c',
  warn: '#fab219',
}
// 連続値の濃淡(暗い面では、暗い=少ない、明るい=多い)
export const RAMP = ['#10241d', '#134e4a', '#115e59', '#0f766e', '#0d9488', '#14b8a6', '#2dd4bf', '#99f6e4']
export const rampColor = (v: number | null | undefined, cuts: number[]) =>
  v == null ? 'transparent' : RAMP[Math.min(RAMP.length - 1, cuts.filter(c => v >= c).length)]

export const hm = (m: number) => `${Math.floor(m / 60)}:${String(Math.round(m % 60)).padStart(2, '0')}`
export const pct = (v: number | null | undefined, d = 0) => (v == null ? '-' : `${(v * 100).toFixed(d)}%`)
export const md = (d: string) => `${Number(d.slice(5, 7))}/${Number(d.slice(8, 10))}`
export const mins = (v: number | null | undefined) => (v == null ? '-' : `${Math.round(v)}分`)

export function Card({ title, note, children, className = '' }: { title: React.ReactNode; note?: React.ReactNode; children: React.ReactNode; className?: string }) {
  return (
    <section className={`min-w-0 bg-zinc-900/50 border border-zinc-800/70 rounded-2xl p-4 sm:p-5 space-y-4 ${className}`}>
      <div className="flex flex-wrap items-baseline justify-between gap-2">
        <h3 className="text-sm font-semibold text-zinc-100">{title}</h3>
        {note && <div className="text-xs text-zinc-500">{note}</div>}
      </div>
      {children}
    </section>
  )
}

export function Tile({ icon, label, value, sub }: { icon?: React.ReactNode; label: string; value: React.ReactNode; sub?: React.ReactNode }) {
  return (
    <div className="min-w-0 bg-zinc-900/60 border border-zinc-800/80 rounded-2xl p-4">
      <div className="flex items-center gap-1.5 text-xs text-zinc-500">{icon}{label}</div>
      <div className="mt-1.5 text-xl sm:text-2xl font-bold text-white tabular-nums">{value}</div>
      {sub && <div className="mt-0.5 text-xs text-zinc-500">{sub}</div>}
    </div>
  )
}

export function Segmented<T extends string>({ value, options, onChange }: { value: T; options: [T, string][]; onChange: (v: T) => void }) {
  return (
    <div className="inline-flex flex-wrap rounded-xl border border-zinc-800 bg-zinc-900/60 p-0.5">
      {options.map(([v, label]) => (
        <button key={v} onClick={() => onChange(v)}
          className={`px-3 py-1 text-xs rounded-lg transition-colors ${value === v ? 'bg-teal-500/15 text-teal-300' : 'text-zinc-400 hover:text-zinc-200'}`}>
          {label}
        </button>
      ))}
    </div>
  )
}

export function TipBox({ children }: { children: React.ReactNode }) {
  return <div className="bg-zinc-900 border border-zinc-700 rounded-xl px-3 py-2 text-xs shadow-xl space-y-0.5">{children}</div>
}

/** 合否(色だけに頼らず、アイコンと文字も付ける) */
export function Status({ ok, children }: { ok: boolean | null; children?: React.ReactNode }) {
  if (ok == null) return <span className="inline-flex items-center gap-1 text-zinc-500"><CircleDashed size={12} aria-hidden />{children ?? '未計算'}</span>
  const Icon = ok ? CheckCircle2 : AlertTriangle
  return (
    <span className="relative inline-flex items-center gap-1 text-zinc-200">
      <Icon size={12} color={ok ? C.good : C.warn} aria-hidden />
      <span className="sr-only">{ok ? '合格' : '不合格'}</span>
      {children ?? (ok ? '合格' : '不合格')}
    </span>
  )
}

export function Code({ children }: { children: React.ReactNode }) {
  return <code className="text-teal-300 bg-teal-500/10 rounded px-1 py-0.5 text-[11px]">{children}</code>
}

/** 計画書の問い(Q1〜Q8)の枠。必要な日数に届いていなければ「参考値」と明示する */
export function QSection({ q, title, method, source, minDays, first, dataDays, ready, missing, calc, children }: {
  q: string; title: string; method: string; source: string; minDays: number; first: string; dataDays: number
  ready: boolean; missing?: React.ReactNode; calc?: { at: string | null; days: number | null }; children?: React.ReactNode
}) {
  const short = dataDays < minDays
  const stale = calc?.days != null && calc.days < dataDays
  return (
    <section className="min-w-0 bg-zinc-900/50 border border-zinc-800/70 rounded-2xl p-4 sm:p-5 space-y-4">
      <div className="space-y-1.5">
        <div className="flex flex-wrap items-center gap-2">
          <span className="text-xs font-bold text-teal-300 bg-teal-500/10 border border-teal-500/20 rounded-md px-1.5 py-0.5">{q}</span>
          <h3 className="text-sm font-semibold text-zinc-100">{title}</h3>
        </div>
        <div className="flex flex-wrap gap-x-4 gap-y-1 text-xs text-zinc-500">
          <span>手法:{method}</span>
          <span>出力:{source}</span>
          <span>必要なデータ:{minDays}日〜(いま{dataDays}日)</span>
          <span>初回:{first}</span>
          {calc?.at && <span>計算:{calc.at}{calc.days != null ? `・${calc.days}日分` : ''}</span>}
        </div>
      </div>
      {!ready ? (
        <div className="rounded-xl border border-dashed border-zinc-700 px-4 py-6 text-center text-xs text-zinc-400 space-y-1">
          {short ? <p><Clock size={12} className="inline mr-1" aria-hidden />あと{minDays - dataDays}日分たまると解禁({first}の予定)</p> : null}
          {missing && <p>{missing}</p>}
        </div>
      ) : (
        <>
          {short && (
            <p className="rounded-lg border border-amber-500/30 bg-amber-500/10 px-3 py-1.5 text-xs text-amber-200">
              参考値:計画書の必要日数({minDays}日)に届いていません
            </p>
          )}
          {stale && (
            <p className="rounded-lg border border-amber-500/30 bg-amber-500/10 px-3 py-1.5 text-xs text-amber-200">
              計算結果が古い({calc?.days}日分で計算。いまは{dataDays}日分)。月曜の作業で再実行してください
            </p>
          )}
          {children}
        </>
      )}
    </section>
  )
}
