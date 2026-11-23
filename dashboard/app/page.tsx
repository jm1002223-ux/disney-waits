import { readFile } from 'node:fs/promises'
import path from 'node:path'
import { AppShell } from './components/AppShell'
import { Dashboard } from './components/Dashboard'
import type { ParkData } from './lib/types'

// DASHBOARD_DATA_DIR を指定すると、そこにある集計(ダミーなど)を読む。画面にはサンプル表示の帯を出す
const SAMPLE_DIR = process.env.DASHBOARD_DATA_DIR

async function load(park: string): Promise<ParkData | null> {
  try {
    const raw = await readFile(path.join(SAMPLE_DIR || path.join(process.cwd(), 'data'), `${park}.json`), 'utf-8')
    return JSON.parse(raw) as ParkData
  } catch {
    return null
  }
}

export default async function Page() {
  const parks = (await Promise.all(['DL', 'DCA'].map(load))).filter((p): p is ParkData => p !== null)
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
