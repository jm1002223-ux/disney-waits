import { readFile } from 'node:fs/promises'
import path from 'node:path'
import { AppShell } from '../components/AppShell'
import { Lab } from './Lab'
import type { ParkData } from '../lib/types'

// 見せ方の試作ページ(Q1)。本体のダッシュボードと同じ集計JSONを読む
const SAMPLE_DIR = process.env.DASHBOARD_DATA_DIR

async function load(park: string): Promise<ParkData | null> {
  try {
    const raw = await readFile(path.join(SAMPLE_DIR || path.join(process.cwd(), 'data'), `${park}.json`), 'utf-8')
    return JSON.parse(raw) as ParkData
  } catch {
    return null
  }
}

export default async function LabPage() {
  const parks = (await Promise.all(['DL', 'DCA'].map(load))).filter((p): p is ParkData => p !== null)
  const updatedAt = parks.map(p => p.generated_at).sort().at(-1)
  return (
    <AppShell updatedAt={updatedAt}>
      {parks.length ? <Lab parks={parks} /> : <p className="text-sm text-zinc-400">集計データがありません。</p>}
    </AppShell>
  )
}
