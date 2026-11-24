import { readFile } from 'node:fs/promises'
import path from 'node:path'
import type { ParkData } from './types'

// DASHBOARD_DATA_DIR を指定すると、そこにある集計(ダミーなど)を読む。画面にはサンプル表示の帯を出す
export const SAMPLE_DIR = process.env.DASHBOARD_DATA_DIR

// 公開版(本番):GitHub Actions が1時間おきに書き出してコミットする集計(リポジトリの summary/)を読む。
// 5分ごとに読み直すので、置き直さなくても最新になる。読めないときは、置いたときの dashboard/data/ を使う
const REMOTE = process.env.DASHBOARD_DATA_URL ?? 'https://raw.githubusercontent.com/jm1002223-ux/disney-waits/main/summary'

export async function loadPark(park: string): Promise<ParkData | null> {
  if (!SAMPLE_DIR && process.env.NODE_ENV === 'production') {
    try {
      const r = await fetch(`${REMOTE}/${park}.json`, { next: { revalidate: 300 } })
      if (r.ok) return (await r.json()) as ParkData
    } catch {
      // 下の手元のファイルを使う
    }
  }
  try {
    const raw = await readFile(path.join(SAMPLE_DIR || path.join(process.cwd(), 'data'), `${park}.json`), 'utf-8')
    return JSON.parse(raw) as ParkData
  } catch {
    return null
  }
}
