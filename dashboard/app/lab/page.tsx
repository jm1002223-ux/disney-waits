import { AppShell } from '../components/AppShell'
import { Lab } from './Lab'
import { loadPark } from '../lib/load'
import type { ParkData } from '../lib/types'


export const revalidate = 300 // 5分ごとに集計を読み直す

export default async function LabPage() {
  const parks = (await Promise.all(['DL', 'DCA', 'TDL', 'TDS'].map(loadPark))).filter((p): p is ParkData => p !== null)
  const updatedAt = parks.map(p => p.generated_at).sort().at(-1)
  return (
    <AppShell updatedAt={updatedAt}>
      {parks.length ? <Lab parks={parks} /> : <p className="text-sm text-zinc-400">集計データがありません。</p>}
    </AppShell>
  )
}
