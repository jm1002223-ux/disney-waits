'use client'

import { useState } from 'react'
import { Segmented, Status } from './ui'
import { TabQuality } from './TabQuality'
import { TabBasic } from './TabBasic'
import { TabModel } from './TabModel'
import { TabPeak } from './TabPeak'
import { TabPlan } from './TabPlan'
import type { ParkData } from '../lib/types'

// 分析計画書の「成果物」と「スケジュール」の表をそのまま並べる
type TabId = 'quality' | 'basic' | 'model' | 'peak' | 'plan'
const PHASES: { id: TabId; no: string; due: string; title: string; content: string; days: number; ready: (d: ParkData) => boolean }[] = [
  { id: 'quality', no: '①', due: '11/30(月)', title: 'データ品質レポート', content: '取得の抜け漏れ、実行間隔、アトラクション名の対応', days: 7, ready: d => d.data_days >= 1 },
  { id: 'basic', no: '②', due: '12/7(月)', title: '基礎分析', content: 'Q1 時間帯の傾向・平日と週末、Q2 混雑指数、Q6 朝いちばん、Q7 シス調', days: 14, ready: d => !!d.q6 && !!d.q7 },
  { id: 'model', no: '③', due: '12/14(月)', title: '予測モデルと分類', content: 'Q3 混雑指数モデルとGBM、Q4 精度検証、Q5 クラスタリング', days: 21, ready: d => !!d.q3 && !!d.q4 && !!d.q5 },
  { id: 'peak', no: '④', due: '12/21(月)', title: '繁忙期の反映', content: 'クリスマス前を加えたモデル更新、Q8 ショー中の空き・ゲスト占有率', days: 28, ready: d => d.q8.occupancy.rides.length > 0 },
  { id: 'plan', no: '⑤', due: '12/26(土)', title: '最終プラン', content: '両パークの回り方、省略候補、判定のまとめ', days: 33, ready: d => !!d.plan },
]

export function Dashboard({ parks }: { parks: ParkData[] }) {
  const [parkId, setParkId] = useState(parks[0].park)
  const [tab, setTab] = useState<TabId>('quality')
  const d = parks.find(p => p.park === parkId) ?? parks[0]
  const phase = PHASES.find(p => p.id === tab)!

  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <h1 className="text-xl font-bold text-white">{d.park_name}</h1>
          <p className="text-xs text-zinc-500 mt-1">分析計画書(11/24〜12/26)の成果物の順に表示。時刻は現地(太平洋時間)。いま{d.data_days}日分</p>
        </div>
        <Segmented value={parkId} options={parks.map(p => [p.park, p.park] as [string, string])} onChange={setParkId} />
      </div>

      {/* 成果物のタブ(期限・中身・使えるデータの目安) */}
      <nav className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-5 gap-2" aria-label="成果物">
        {PHASES.map(p => {
          const on = p.id === tab, ok = p.ready(d)
          return (
            <button key={p.id} onClick={() => setTab(p.id)} aria-current={on ? 'page' : undefined}
              className={`text-left rounded-xl border px-3 py-2.5 transition-colors ${on ? 'border-teal-500/40 bg-teal-500/10' : 'border-zinc-800 bg-zinc-900/40 hover:border-zinc-700'}`}>
              <div className="flex items-center justify-between gap-2">
                <span className={`text-xs font-semibold ${on ? 'text-teal-300' : 'text-zinc-200'}`}>{p.no} {p.title}</span>
              </div>
              <div className="mt-0.5 text-[11px] text-zinc-500">期限 {p.due}</div>
              <div className="mt-1 text-[11px]">
                <Status ok={ok ? true : null}>{ok ? '表示できる' : 'データ待ち'}</Status><span className="ml-2 text-zinc-600">計画のデータ 〜{p.days}日</span>
              </div>
            </button>
          )
        })}
      </nav>
      <p className="text-xs text-zinc-400 -mt-3">{phase.no} {phase.title}:{phase.content}</p>

      {tab === 'quality' && <TabQuality d={d} />}
      {tab === 'basic' && <TabBasic key={d.park} d={d} />}
      {tab === 'model' && <TabModel key={d.park} d={d} />}
      {tab === 'peak' && <TabPeak key={d.park} d={d} />}
      {tab === 'plan' && <TabPlan d={d} />}
    </div>
  )
}
