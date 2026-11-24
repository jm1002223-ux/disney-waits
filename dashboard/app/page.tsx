import { AppShell } from './components/AppShell'
import { Dashboard } from './components/Dashboard'
import { SAMPLE_DIR, loadPark } from './lib/load'
import type { ParkData } from './lib/types'


export const revalidate = 300 // 5分ごとに集計を読み直す

export default async function Page() {
  const parks = (await Promise.all(['DL', 'DCA'].map(loadPark))).filter((p): p is ParkData => p !== null)
  const updatedAt = parks.map(p => p.generated_at).sort().at(-1)

  return (
    <AppShell updatedAt={updatedAt}>
      {SAMPLE_DIR && (
        <div className="mb-6 rounded-xl border border-amber-500/30 bg-amber-500/10 px-4 py-2 text-xs text-amber-200">
          サンプル表示中:ダミーデータです(本物の待ち時間ではありません)
        </div>
      )}
      {parks.length ? (
        <Dashboard parks={parks} />
      ) : (
        <div className="rounded-2xl border border-zinc-800/60 bg-zinc-900/30 px-5 py-16 text-center text-sm text-zinc-400">
          集計データがありません。リポジトリの直下で <code className="text-teal-300">python warehouse.py</code> →{' '}
          <code className="text-teal-300">python export_dashboard.py</code> を実行してください。
        </div>
      )}
    </AppShell>
  )
}
