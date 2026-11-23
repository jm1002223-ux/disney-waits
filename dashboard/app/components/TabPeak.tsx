'use client'

import { useState } from 'react'
import { Card, QSection, pct, rampColor } from './ui'
import { CrowdIndex, Legend } from './TabBasic'
import type { ParkData } from '../lib/types'

const S_CUTS = [0.02, 0.04, 0.06, 0.08, 0.1, 0.12, 0.15]

/* ── タブ④ 繁忙期の反映(12/21):モデル更新・Q8 ── */
export function TabPeak({ d }: { d: ParkData }) {
  const showNames = Array.from(new Set(d.q8.shows.map(s => s.show)))
  const [show, setShow] = useState(showNames[0] ?? '')
  const rows = d.q8.shows.filter(s => s.show === show).sort((a, b) => (a.change ?? 0) - (b.change ?? 0))
  const occ = d.q8.occupancy
  const xm = d.special.christmas

  return (
    <div className="space-y-6">
      <Card title="クリスマス前を加えた混雑指数" note={`${xm?.label}(${xm?.from.slice(5)}〜${xm?.to.slice(5)})を基準に含める/除くを比べる`}>
        <CrowdIndex d={d} variants={['all', 'ex_christmas', 'ex_both']} />
        <p className="text-xs text-zinc-500">
          予測モデル(③のQ3・Q4)は、月曜の作業で <code className="text-teal-300">model.py</code> と <code className="text-teal-300">gbm.py</code> を再実行すると、クリスマス前のデータを含めて更新されます。旅行日がこの周辺なら、この期間のデータを重めに見ます。
        </p>
      </Card>

      <QSection q="Q8" title="ショー中にどこが空くか、ゲストはどこに偏るか" method="ショー前後の比較(直前30分 → ショー中)、リトルの法則で占有率" source="ノート⑤⑦"
        minDays={7} first="12/21" dataDays={d.data_days} ready={d.q8.shows.length > 0 || occ.rides.length > 0}
        missing={<>shows.csv の時刻と、warehouse.py の再実行が必要です</>}>
        {showNames.length > 0 && (
          <div className="space-y-2">
            <p className="text-xs text-zinc-400">ショー中に空くアトラクション(直前30分の平均待ちが15分以上のもの。マイナスほど空く)</p>
            <select value={show} onChange={e => setShow(e.target.value)} className="bg-zinc-900 border border-zinc-800 rounded-xl px-3 py-1.5 text-xs text-zinc-200 max-w-full">
              {showNames.map(s => <option key={s} value={s}>{s}</option>)}
            </select>
            <div className="overflow-x-auto">
              <table className="w-full text-xs">
                <thead className="text-zinc-500"><tr className="border-b border-zinc-800">
                  {['アトラクション', '直前30分', 'ショー中', '変化', '日数'].map((h, i) => <th key={h} className={`py-2 px-2 font-normal ${i === 0 ? 'text-left' : 'text-right'} whitespace-nowrap`}>{h}</th>)}
                </tr></thead>
                <tbody>
                  {rows.slice(0, 10).map(r => (
                    <tr key={r.no} className="border-b border-zinc-800/50">
                      <td className="py-1.5 px-2 text-zinc-200 whitespace-nowrap">{r.no}. {r.name}</td>
                      <td className="py-1.5 px-2 text-right tabular-nums text-zinc-300">{r.before != null ? `${Math.round(r.before)}分` : '-'}</td>
                      <td className="py-1.5 px-2 text-right tabular-nums text-zinc-300">{r.during != null ? `${Math.round(r.during)}分` : '-'}</td>
                      <td className="py-1.5 px-2 text-right tabular-nums text-zinc-100">{r.change != null ? `${r.change > 0 ? '+' : ''}${Math.round(r.change)}%` : '-'}</td>
                      <td className="py-1.5 px-2 text-right tabular-nums text-zinc-500">{r.days}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
            <p className="text-xs text-zinc-500">時刻:{rows[0]?.time}(shows.csv。公式アプリの時刻に合わせて手で直す)</p>
          </div>
        )}
        {occ.rides.length > 0 && (
          <div className="pt-3 border-t border-zinc-800/60 space-y-2">
            <div className="flex flex-wrap items-center justify-between gap-2 text-xs text-zinc-400">
              <span>ゲスト占有率:列に並んでいる人(推定)のうち、各アトラクションの割合(上位8件、2時間ごと)</span>
              <Legend cuts={S_CUTS.map(x => x * 100)} unit="%" low="低い" high="高い" />
            </div>
            <div className="overflow-x-auto">
              <table className="text-xs border-separate" style={{ borderSpacing: 2 }}>
                <thead><tr><th className="sticky left-0 bg-[#141f1b] z-10" />{occ.blocks.map(b => <th key={b} className="font-normal text-zinc-500 px-1 text-center whitespace-nowrap">{b}時〜</th>)}</tr></thead>
                <tbody>
                  {occ.rides.map(r => (
                    <tr key={r.no}>
                      <td className="sticky left-0 z-10 bg-[#141f1b] pr-3 py-0.5 whitespace-nowrap max-w-56 truncate text-zinc-400">{r.no}. {r.name}</td>
                      {occ.blocks.map(b => {
                        const v = r.share[String(b)]
                        return <td key={b} className="h-6 min-w-12 rounded-[4px] text-center tabular-nums text-zinc-100" style={{ background: rampColor(v, S_CUTS) }}>{pct(v)}</td>
                      })}
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
            <p className="text-xs text-zinc-500">処理人数は公表値がない推定値なので、傾向を見る目安として使います(計画書)。</p>
          </div>
        )}
      </QSection>
    </div>
  )
}
