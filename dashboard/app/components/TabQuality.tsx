'use client'

import { AlertTriangle, CalendarDays, Database, Gauge, Timer } from 'lucide-react'
import { C, Card, Status, Tile, md, pct } from './ui'
import type { Criterion, ParkData } from '../lib/types'

/** 品質の判定基準(計画書の表と同じ6項目) */
export function CriteriaTable({ criteria, dataDays }: { criteria: Criterion[]; dataDays: number }) {
  return (
    <div className="overflow-x-auto">
      <table className="w-full text-xs">
        <thead className="text-zinc-500">
          <tr className="border-b border-zinc-800">
            {['指標', '測り方', '合格ライン', 'いまの値', '判定', '下回ったら'].map(h => (
              <th key={h} className="py-2 px-2 font-normal text-left whitespace-nowrap">{h}</th>
            ))}
          </tr>
        </thead>
        <tbody>
          {criteria.map(c => (
            <tr key={c.id} className="border-b border-zinc-800/50 align-top">
              <td className="py-2 px-2 text-zinc-100 whitespace-nowrap">{c.name}</td>
              <td className="py-2 px-2 text-zinc-400 min-w-48">{c.how}</td>
              <td className="py-2 px-2 text-zinc-300 whitespace-nowrap">{c.line}</td>
              <td className="py-2 px-2 text-zinc-100 tabular-nums whitespace-nowrap">{c.value ?? '-'}</td>
              <td className="py-2 px-2 whitespace-nowrap">
                {c.ok == null
                  ? <Status ok={null}>{c.min_days && dataDays < c.min_days ? `${c.min_days}日分から` : `未計算(${c.source})`}</Status>
                  : <Status ok={c.ok} />}
              </td>
              <td className="py-2 px-2 text-zinc-400 min-w-48">{c.fallback}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}

export function TabQuality({ d }: { d: ParkData }) {
  const cov = d.range.coverage
  const low = d.days.filter(x => x.coverage != null && x.coverage < 0.9)
  return (
    <div className="space-y-6">
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-3">
        <Tile icon={<CalendarDays size={12} />} label="データの日数" value={`${d.range.days}日分`} sub={`${md(d.range.from)}〜${md(d.range.to)}`} />
        <Tile icon={<Gauge size={12} />} label="データの充足率(平均)" value={cov == null ? '-' : <Status ok={cov >= 0.9}><span className="text-xl sm:text-2xl">{pct(cov)}</span></Status>} sub="合格ライン 90%" />
        <Tile icon={<Database size={12} />} label="記録" value={d.range.rows.toLocaleString()} sub={`アトラクション ${d.rides.length}`} />
        <Tile icon={<Timer size={12} />} label="最後の取得(現地)" value={d.range.last_fetch?.slice(11) ?? '-'} sub={d.range.last_fetch?.slice(0, 10)} />
      </div>

      <Card title="品質の判定基準" note="各フェーズの終わり(月曜)にこの表で判定し、下回ったら右端のとおりにする">
        <CriteriaTable criteria={d.criteria} dataDays={d.data_days} />
      </Card>

      <Card title="取得の抜け漏れと実行間隔" note="充足率 = 営業時間(推定)の15分枠のうち、記録がある割合">
        <div className="overflow-x-auto">
          <table className="w-full text-xs">
            <thead className="text-zinc-500">
              <tr className="border-b border-zinc-800">
                {['日付', '営業(推定)', '記録のある15分枠', '充足率', '取得回数', '間隔(中央・最大)', '扱い'].map((h, i) => (
                  <th key={h} className={`py-2 px-2 font-normal ${i === 0 ? 'text-left' : 'text-right'} whitespace-nowrap`}>{h}</th>
                ))}
              </tr>
            </thead>
            <tbody>
              {d.days.map(x => {
                const sp = Object.values(d.special).find(s => x.date >= s.from && x.date <= s.to)
                return (
                  <tr key={x.date} className="border-b border-zinc-800/50">
                    <td className="py-1.5 px-2 text-zinc-200 whitespace-nowrap">
                      {md(x.date)}({x.weekday}){x.holiday ? ` ${x.holiday}` : ''}{sp ? <span className="ml-1 text-zinc-500">[{sp.label}]</span> : null}
                    </td>
                    <td className="py-1.5 px-2 text-right tabular-nums text-zinc-400 whitespace-nowrap">{x.open ? `${x.open}〜${x.close}` : '-'}</td>
                    <td className="py-1.5 px-2 text-right tabular-nums text-zinc-300 whitespace-nowrap">{x.slots} / {x.expected}</td>
                    <td className="py-1.5 px-2 text-right tabular-nums">{x.coverage == null ? '-' : <Status ok={x.coverage >= 0.9}>{pct(x.coverage)}</Status>}</td>
                    <td className="py-1.5 px-2 text-right tabular-nums text-zinc-400">{x.runs}</td>
                    <td className="py-1.5 px-2 text-right tabular-nums text-zinc-400 whitespace-nowrap">{x.median_gap ?? '-'}分・{x.max_gap ?? '-'}分</td>
                    <td className="py-1.5 px-2 text-right text-zinc-400 whitespace-nowrap">
                      {x.coverage != null && x.coverage < 0.9 ? '分析から外す候補' : '使う'}
                    </td>
                  </tr>
                )
              })}
            </tbody>
          </table>
        </div>
        <p className="text-xs text-zinc-500">
          {low.length ? <>90%未満の日:{low.map(x => md(x.date)).join('、')}(実行ログを確認し、大きな欠けなら分析から外す)</> : '90%未満の日はありません'}
        </p>
      </Card>

      <Card title="アトラクション名の対応" note="rides.json(対応表)にない名前が記録に出ていないか">
        {d.unmatched.length ? (
          <div className="space-y-2 text-xs">
            <p className="text-zinc-300">
              <AlertTriangle size={12} className="inline mr-1" color={C.warn} aria-hidden />
              対応表にない名前が{d.unmatched.length}件あります。分析から漏れるので、新しいアトラクションなら rides.json に足す
            </p>
            <ul className="grid sm:grid-cols-2 gap-x-6 gap-y-0.5 text-zinc-400">
              {d.unmatched.map(u => <li key={u.id}>{u.name}(ID {u.id})</li>)}
            </ul>
          </div>
        ) : <p className="text-xs text-zinc-400"><Status ok={true}>対応表にない名前はありません</Status></p>}
      </Card>
    </div>
  )
}
