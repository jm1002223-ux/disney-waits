'use client'

import { Card, Status, Tile } from './ui'
import { CriteriaTable } from './TabQuality'
import type { ParkData } from '../lib/types'

/* ── タブ⑤ 最終プラン(12/26):回り方・省略候補・判定のまとめ ── */
export function TabPlan({ d }: { d: ParkData }) {
  const p = d.plan
  const failed = d.criteria.filter(c => c.ok === false)
  return (
    <div className="space-y-6">
      <Card title="判定のまとめ" note="下回った指標があれば、プランは中央値(混雑指数なし)で計算する(計画書)">
        {failed.length
          ? <p className="text-xs text-amber-200">合格ラインを下回った指標:{failed.map(c => c.name).join('、')}</p>
          : <p className="text-xs text-zinc-400"><Status ok={d.criteria.every(c => c.ok)}>{d.criteria.every(c => c.ok) ? 'すべて合格' : 'まだ判定できない指標があります'}</Status></p>}
        <CriteriaTable criteria={d.criteria} dataDays={d.data_days} />
      </Card>

      {!p ? (
        <div className="rounded-2xl border border-dashed border-zinc-700 px-4 py-10 text-center text-xs text-zinc-400">
          プランの結果がありません。<code className="text-teal-300">python plan.py plan_{d.park}.json</code> を実行してください(旅行日が決まったら plan_{d.park}.json の date と crowd_index を入れる)
        </div>
      ) : <>
        <div className="grid grid-cols-2 lg:grid-cols-4 gap-3">
          <Tile label="旅行日(設定)" value={p.date ?? '未定'} sub={`入園 ${p.entry}・退園 ${p.exit}`} />
          <Tile label="プランの余裕" value={`${p.slack_min}分`} sub={<Status ok={p.slack_min >= 30}>合格ライン 30分以上</Status>} />
          <Tile label="乗れるアトラクション" value={`${p.with_ll.rides}個`} sub={`ショー ${p.with_ll.shows}つ`} />
          <Tile label="待ち時間の合計" value={`${Math.floor(p.with_ll.wait_min / 60)}時間${p.with_ll.wait_min % 60}分`} sub={`最後の予定 ${p.with_ll.end}`} />
        </div>
        {p.slack_min < 30 && <p className="text-xs text-amber-200">余裕が30分未満です。下の「省略候補」の上から外して計算し直します(計画書)。</p>}

        <Card title="回り方" note={`待ち時間:${p.wait_source}`}>
          <div className="overflow-x-auto">
            <table className="w-full text-xs">
              <thead className="text-zinc-500"><tr className="border-b border-zinc-800">
                {['時刻', 'やること', '種類', '待ち', '徒歩', '備考'].map((h, i) => <th key={h} className={`py-2 px-2 font-normal ${i < 3 || i === 5 ? 'text-left' : 'text-right'} whitespace-nowrap`}>{h}</th>)}
              </tr></thead>
              <tbody>
                {p.steps.map((s, i) => (
                  <tr key={i} className={`border-b border-zinc-800/50 ${s.kind === 'LL' ? 'bg-teal-500/[0.05]' : ''}`}>
                    <td className="py-1.5 px-2 tabular-nums text-zinc-300">{s.time}</td>
                    <td className="py-1.5 px-2 text-zinc-100 whitespace-nowrap">{s.name}</td>
                    <td className="py-1.5 px-2 text-zinc-400 whitespace-nowrap">{s.tag}</td>
                    <td className="py-1.5 px-2 text-right tabular-nums text-zinc-300">{s.wait}分</td>
                    <td className="py-1.5 px-2 text-right tabular-nums text-zinc-400">{s.walk}分</td>
                    <td className="py-1.5 px-2 text-zinc-400 whitespace-nowrap">{s.note}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </Card>

        {p.multi_pass.length > 0 && (
          <Card title="マルチパスの取り方" note={`優先順位の順に予約。パスで乗り終えるのは ${p.ll_use_until} まで`}>
            <div className="overflow-x-auto">
              <table className="w-full text-xs">
                <thead className="text-zinc-500"><tr className="border-b border-zinc-800">
                  {['順位', 'アトラクション', '判定', '予約', '戻り(見込み)', '乗る', 'その時刻のスタンバイ'].map((h, i) => <th key={h} className={`py-2 px-2 font-normal ${i === 1 || i === 2 ? 'text-left' : 'text-right'} whitespace-nowrap`}>{h}</th>)}
                </tr></thead>
                <tbody>
                  {p.multi_pass.map(r => (
                    <tr key={r.no} className="border-b border-zinc-800/50">
                      <td className="py-1.5 px-2 text-right tabular-nums text-zinc-400">{r.rank ?? '-'}</td>
                      <td className="py-1.5 px-2 text-zinc-200 whitespace-nowrap">{r.no}. {r.name}</td>
                      <td className="py-1.5 px-2 whitespace-nowrap">{r.take ? <span className="text-teal-300 font-semibold">取る</span> : <span className="text-zinc-400">取らない:{r.why}</span>}</td>
                      <td className="py-1.5 px-2 text-right tabular-nums text-zinc-300">{r.book ?? '-'}</td>
                      <td className="py-1.5 px-2 text-right tabular-nums text-zinc-300">{r.return ? `${r.return}〜` : '-'}</td>
                      <td className="py-1.5 px-2 text-right tabular-nums text-zinc-100">{r.use ?? '-'}</td>
                      <td className="py-1.5 px-2 text-right tabular-nums text-zinc-400">{r.standby_then != null ? `${r.standby_then}分` : '-'}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
            {p.without_ll && (
              <p className="text-xs text-zinc-400">
                マルチパスなしの場合:{p.without_ll.rides}個・待ち合計 {Math.floor(p.without_ll.wait_min / 60)}時間{p.without_ll.wait_min % 60}分・最後の予定 {p.without_ll.end}
              </p>
            )}
            <p className="text-xs text-zinc-500">戻り時刻はAPIから取れないため見込み値です。当日アプリの時刻に合わせて計算し直せます。</p>
          </Card>
        )}

        <Card title="省略候補" note="時間内に入らなかったもの(優先度の低い順)">
          {p.skipped.length
            ? <ul className="text-xs text-zinc-300 space-y-0.5">{p.skipped.map(s => <li key={s.name}>{s.name}<span className="text-zinc-500">(優先度 {s.priority})</span></li>)}</ul>
            : <p className="text-xs text-zinc-400">ありません</p>}
        </Card>
      </>}
    </div>
  )
}
