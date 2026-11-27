'use client'

import { useEffect, useRef, useState } from 'react'
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
  // URL の #basic などでタブを開く(リンクを送るとき用)
  useEffect(() => {
    const h = window.location.hash.slice(1)
    if (PHASES.some(p => p.id === h)) setTab(h as TabId)
  }, [])
  const navRef = useRef<HTMLElement>(null)
  useEffect(() => {
    navRef.current?.querySelector('[aria-current="page"]')?.scrollIntoView({ block: 'nearest', inline: 'nearest' })
  }, [tab])
  const choose = (id: TabId) => { setTab(id); window.history.replaceState(null, '', `#${id}`) }
  const d = parks.find(p => p.park === parkId) ?? parks[0]
  const phase = PHASES.find(p => p.id === tab)!

  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <h1 className="text-xl font-bold text-white">{d.park_name}</h1>
          <p className="text-xs text-zinc-500 mt-1">分析計画書(11/24〜12/26)の成果物の順に表示。時刻は現地({d.park === 'TDL' || d.park === 'TDS' ? '日本時間' : '太平洋時間'})。いま{d.data_days}日分</p>
        </div>
        <Segmented value={parkId} options={parks.map(p => [p.park, p.park] as [string, string])} onChange={setParkId} />
      </div>

      {/* 成果物のタブ(期限・中身・使えるデータの目安) */}
      {/* スマホ:横にスクロールする1行。sm以上:カードを並べる */}
      <nav ref={navRef} className="-mx-4 flex snap-x gap-2 overflow-x-auto px-4 pb-1 sm:mx-0 sm:grid sm:grid-cols-3 sm:overflow-visible sm:px-0 sm:pb-0 lg:grid-cols-5" aria-label="成果物">
        {PHASES.map(p => {
          const on = p.id === tab, ok = p.ready(d)
          return (
            <button key={p.id} onClick={() => choose(p.id)} aria-current={on ? 'page' : undefined}
              className={`shrink-0 snap-start text-left rounded-xl border px-3 py-2 sm:py-2.5 transition-colors ${on ? 'border-teal-500/40 bg-teal-500/10' : 'border-zinc-800 bg-zinc-900/40 hover:border-zinc-700'}`}>
              <div className={`whitespace-nowrap text-xs font-semibold ${on ? 'text-teal-300' : 'text-zinc-200'}`}>{p.no} {p.title}</div>
              <div className="mt-0.5 flex items-center gap-2 whitespace-nowrap text-[11px] text-zinc-500">
                <span>〜{p.due}</span>
                <Status ok={ok ? true : null}>{ok ? '表示できる' : 'データ待ち'}</Status>
              </div>
              <div className="mt-1 hidden text-[11px] text-zinc-600 sm:block">計画のデータ 〜{p.days}日</div>
            </button>
          )
        })}
      </nav>
      <p className="text-xs text-zinc-400 -mt-3 sm:-mt-3">{phase.no} {phase.title}:{phase.content}</p>

      {tab === 'quality' && <TabQuality d={d} />}
      {tab === 'basic' && <TabBasic key={d.park} d={d} />}
      {tab === 'model' && <TabModel key={d.park} d={d} />}
      {tab === 'peak' && <TabPeak key={d.park} d={d} />}
      {tab === 'plan' && <TabPlan d={d} />}
    </div>
  )
}
