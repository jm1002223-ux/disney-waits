import { Clock3 } from 'lucide-react'

// music-lesson-portal の AppShell を流用(ログイン・ロール表示を外し、出典表記を足した)
type Props = {
  updatedAt?: string
  children: React.ReactNode
}

export function AppShell({ updatedAt, children }: Props) {
  return (
    <div className="min-h-screen flex flex-col text-zinc-100">
      <header className="sticky top-0 z-40 border-b border-white/[0.06] bg-[#0d1f17]/80 backdrop-blur-xl">
        <div className="max-w-6xl mx-auto px-4 sm:px-6 h-14 flex items-center justify-between">
          <div className="flex items-center gap-3">
            <div className="w-7 h-7 rounded-lg bg-gradient-to-br from-teal-500 to-emerald-600 flex items-center justify-center shrink-0">
              <Clock3 size={13} className="text-white" />
            </div>
            <span className="text-white/70 text-sm font-medium">Disney Waits</span>
            <span className="text-xs font-semibold px-2.5 py-0.5 rounded-full border text-teal-400 bg-teal-500/10 border-teal-500/20">
              Private
            </span>
          </div>
          {updatedAt && <span className="text-xs text-zinc-500">集計 {updatedAt}(日本時間)</span>}
        </div>
      </header>

      <main className="max-w-6xl w-full mx-auto px-4 sm:px-6 py-8 flex-1">{children}</main>

      <footer className="border-t border-white/[0.05]">
        <div className="max-w-6xl mx-auto px-4 sm:px-6 py-4 flex flex-wrap gap-x-4 gap-y-1 text-xs text-zinc-500">
          <span>
            Powered by{' '}
            <a href="https://queue-times.com/" target="_blank" rel="noreferrer" className="text-teal-400 hover:text-teal-300 underline underline-offset-2">
              Queue-Times.com
            </a>
          </span>
          <span>個人の研究用。表示待ち時間がもとで、実際の待ちより長めに出やすい</span>
          <span>ディズニー公式とは関係ありません</span>
        </div>
      </footer>
    </div>
  )
}
