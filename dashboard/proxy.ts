import { NextResponse, type NextRequest } from 'next/server'
import { createHash, timingSafeEqual } from 'node:crypto'

// 親しい人だけに見せるための簡易パスワード(Basic認証)。
// 環境変数 DASHBOARD_PASSWORD が空なら(手元の npm run dev など)パスワードなしで開く。
// ユーザー名は何でもよく、パスワードだけを確かめる。
function same(a: string, b: string) {
  const ha = createHash('sha256').update(a).digest()
  const hb = createHash('sha256').update(b).digest()
  return timingSafeEqual(ha, hb)
}

export function proxy(request: NextRequest) {
  const password = process.env.DASHBOARD_PASSWORD
  if (!password) return NextResponse.next()

  const auth = request.headers.get('authorization') ?? ''
  if (auth.startsWith('Basic ')) {
    try {
      const decoded = atob(auth.slice(6))
      const given = decoded.slice(decoded.indexOf(':') + 1)
      if (same(given, password)) return NextResponse.next()
    } catch {
      // 形式がおかしいときは下の401へ
    }
  }
  return new NextResponse('パスワードが必要です', {
    status: 401,
    headers: { 'WWW-Authenticate': 'Basic realm="disney-waits", charset="UTF-8"' },
  })
}

export const config = {
  matcher: ['/((?!_next/static|favicon.ico).*)'],
}
