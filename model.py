"""混雑指数モデル。貯めた待ち時間から次の3つを作る。

1. 混雑指数(日ごと・時間帯ごと)
   人気アトラクションの待ち時間が「データ全体の平均」の何%か。100 = 平均的な日、120 = 2割混んでいる日。
2. アトラクションごとの「混雑指数への反応」
   1日の平均待ち = a + b × 混雑指数 を最小二乗法で当てはめる。
   さらに時間帯ごとの形(朝は平均の何倍、昼は何倍…)を掛けて、
   「混雑指数が X の日の、Y時台の待ち時間」を予測できるようにする。
3. 列に並んでいる人数の推定(リトルの法則)
   列の人数 ≒ 1時間あたりの処理人数 ÷ 60 × 待ち時間(分)
   → 時間帯ごとに、どのアトラクションの列に何人くらいいるか、全体の何割を占めるか。

使い方:
  python model.py --park DL
  python model.py --park DL --backtest   # 待ち時間予測の精度を検証
出力:
  models/<park>.json          … plan.py が "crowd_index" 指定時に使う
  models/<park>_daily.csv     … 日ごとの混雑指数
  models/<park>_rides.csv     … アトラクションごとの反応(指数80/100/120のときの平均待ち)
  models/<park>_queue.csv     … 時間帯ごとの列の人数(推定)
  models/<park>_report.html   … 上の3つのグラフ(ブラウザで開く)
Powered by Queue-Times.com (https://queue-times.com/)
"""
import argparse, csv, glob, json, os, statistics
from collections import defaultdict
from datetime import datetime, date
from zoneinfo import ZoneInfo

TZ = ZoneInfo("America/Los_Angeles")
SLOT = 15


def load(park):
    seen = set()
    obs = defaultdict(lambda: defaultdict(lambda: defaultdict(list)))  # ride -> day -> slot -> [wait]
    for path in sorted(glob.glob(os.path.join("data", park, "*.csv"))):
        with open(path, newline="", encoding="utf-8") as f:
            for r in csv.DictReader(f):
                if r["is_open"] != "1":
                    continue
                key = (r["ride_id"], r["last_updated"] or r["fetched_utc"])
                if key in seen:
                    continue
                seen.add(key)
                ts = datetime.fromisoformat((r["last_updated"] or r["fetched_utc"]).replace("Z", "+00:00")).astimezone(TZ)
                day = ts.date().isoformat()
                slot = (ts.hour * 60 + ts.minute) // SLOT * SLOT
                obs[r["ride_id"]][day][slot].append(float(r["wait_time"] or 0))
    return obs


def mean(x): return sum(x) / len(x) if x else 0.0


def fit(xs, ys):
    """y = a + b x の最小二乗。点が足りなければ傾き0"""
    if len(xs) < 3 or max(xs) - min(xs) < 1e-6:
        return mean(ys), 0.0, 0.0
    mx, my = mean(xs), mean(ys)
    sxx = sum((x - mx) ** 2 for x in xs); sxy = sum((x - mx) * (y - my) for x, y in zip(xs, ys))
    b = sxy / sxx; a = my - b * mx
    ss = sum((y - my) ** 2 for y in ys); sr = sum((y - (a + b * x)) ** 2 for x, y in zip(xs, ys))
    return a, b, (1 - sr / ss) if ss > 0 else 0.0


def load_w(park):
    rides = json.load(open("rides.json", encoding="utf-8"))[park]
    by_qid = {str(v["queue_times_id"]): k for k, v in rides.items()}
    raw = load(park)
    if not raw:
        raise SystemExit(f"data/{park}/ にデータがありません")
    # ride番号 -> day -> slot -> 平均待ち
    W = {}
    for qid, days in raw.items():
        if qid in by_qid:
            W[by_qid[qid]] = {d: {s: mean(v) for s, v in sl.items()} for d, sl in days.items()}
    return rides, W


def day_ci(W, d, overall, core):
    rs = [mean(list(W[k][d].values())) / overall[k] for k in core if d in W[k] and overall.get(k, 0) > 0]
    return 100 * mean(rs) if rs else None


def fit_model(W, rides, use_days):
    """use_days の日だけで、混雑指数とアトラクションごとのモデルを作る"""
    use = set(use_days)
    core = [k for k in W if rides[k]["fallback_peak"] >= 40]
    overall = {k: mean([w for d, sl in W[k].items() if d in use for w in sl.values()]) for k in W}
    daily_ci = {}
    for d in sorted(use):
        v = day_ci(W, d, overall, core)
        if v is not None:
            daily_ci[d] = v
    slot_ci = defaultdict(list)
    for d in daily_ci:
        for s in range(0, 24 * 60, SLOT):
            rs = [W[k][d][s] / overall[k] for k in core if d in W[k] and s in W[k][d] and overall[k] > 0]
            if rs:
                slot_ci[s].append(100 * mean(rs))
    slot_ci = {s: mean(v) for s, v in sorted(slot_ci.items())}
    model = {}
    for k, dd in W.items():
        xs, ys = [], []
        shape = defaultdict(list)
        for d, sl in dd.items():
            if d not in daily_ci:
                continue
            dm = mean(list(sl.values()))
            xs.append(daily_ci[d]); ys.append(dm)
            if dm > 0:
                for s, w in sl.items():
                    shape[s].append(w / dm)
        if not xs:
            continue
        a, b, r2 = fit(xs, ys)
        model[k] = {"a": a, "b": b, "r2": r2, "days": len(xs),
                    "shape": {str(s): round(mean(v), 3) for s, v in sorted(shape.items())}}
    return daily_ci, slot_ci, model, overall, core


def build(park):
    rides, W = load_w(park)
    days = sorted({d for r in W.values() for d in r})
    daily_ci, slot_ci, model, _, _ = fit_model(W, rides, days)
    return rides, days, daily_ci, slot_ci, model


def backtest(park):
    """1日ずつ隠して、残りの日で作ったモデルで隠した日を予測し、実際との差を測る(リーブワンアウト)"""
    rides, W = load_w(park)
    days = sorted({d for r in W.values() for d in r})
    if len(days) < 5:
        raise SystemExit(f"検証には5日分以上のデータが必要です(今は{len(days)}日分)")
    err = {"known": defaultdict(list), "unknown": defaultdict(list), "naive": defaultdict(list)}
    per_day = []
    for test in days:
        train = [d for d in days if d != test]
        dci, _, model, overall, core = fit_model(W, rides, train)
        ci_true = day_ci(W, test, overall, core)
        wd = date.fromisoformat(test).weekday() >= 5
        same = [v for d, v in dci.items() if (date.fromisoformat(d).weekday() >= 5) == wd]
        ci_guess = mean(same) if same else 100.0
        # 比較用:混雑指数を使わず、過去の同じ時間帯の平均だけで予測
        naive = {k: {s: mean([W[k][d][s] for d in train if d in W[k] and s in W[k][d]] or [0]) for s in W[k].get(test, {})} for k in W}
        de = []
        for k, m in model.items():
            for s, actual in W[k].get(test, {}).items():
                if ci_true is not None:
                    e = abs(predict(m, s, ci_true) - actual); err["known"][k].append(e); de.append(e)
                err["unknown"][k].append(abs(predict(m, s, ci_guess) - actual))
                err["naive"][k].append(abs(naive[k].get(s, 0) - actual))
        per_day.append((test, ci_true, ci_guess, mean(de)))
    os.makedirs("models", exist_ok=True)
    with open(f"models/{park}_backtest.csv", "w", newline="", encoding="utf-8-sig") as f:
        w = csv.writer(f)
        w.writerow(["番号", "アトラクション", "平均誤差(指数が分かっている場合・分)", "平均誤差(指数を曜日の平均で仮定・分)", "平均誤差(指数なし・過去の平均だけ・分)", "比較した数"])
        for k in sorted(err["known"], key=lambda k: -mean(err["known"][k])):
            w.writerow([k, rides[k]["name"], round(mean(err["known"][k]), 1), round(mean(err["unknown"][k]), 1), round(mean(err["naive"][k]), 1), len(err["known"][k])])
        w.writerow([]); w.writerow(["日付", "実際の混雑指数", "曜日の平均から仮定した指数", "その日の平均誤差(分)"])
        for d, t, g, e in per_day:
            w.writerow([d, round(t) if t is not None else "", round(g), round(e, 1)])
    allv = lambda key: mean([e for v in err[key].values() for e in v])
    top = [k for k in rides if rides[k]["fallback_peak"] >= 60 and k in err["known"]]
    topv = lambda key: mean([e for k in top for e in err[key][k]]) if top else 0
    # ダッシュボード(export_dashboard.py)用の要約。計算は上と同じ
    json.dump({"park": park, "days": len(days), "top_rides": top,
               "all": {k: round(allv(k), 2) for k in ("known", "unknown", "naive")},
               "top": {k: round(topv(k), 2) for k in ("known", "unknown", "naive")},
               "rides": {k: {"known": round(mean(err["known"][k]), 1), "unknown": round(mean(err["unknown"][k]), 1),
                             "naive": round(mean(err["naive"][k]), 1), "n": len(err["known"][k])} for k in err["known"]},
               "per_day": [{"date": d, "ci_true": round(t, 1) if t is not None else None, "ci_guess": round(g, 1), "err": round(e, 2)}
                           for d, t, g, e in per_day]},
              open(f"models/{park}_backtest_summary.json", "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print(f"{park}: {len(days)}日分で検証しました(1日ずつ隠して予測)")
    print(f"  平均誤差(全アトラクション)  指数が分かっている場合 ±{allv('known'):.1f}分 / 指数を曜日の平均で仮定 ±{allv('unknown'):.1f}分 / 指数なし ±{allv('naive'):.1f}分")
    print(f"  平均誤差(人気アトラクション) 指数が分かっている場合 ±{topv('known'):.1f}分 / 指数を曜日の平均で仮定 ±{topv('unknown'):.1f}分 / 指数なし ±{topv('naive'):.1f}分")
    print(f"  → models/{park}_backtest.csv(アトラクション別・日別の誤差)")


def predict(m, slot, ci):
    """混雑指数ci の日の、slot(分)の待ち時間"""
    base = max(0.0, m["a"] + m["b"] * ci)
    sh = {int(s): v for s, v in m["shape"].items()}
    if not sh:
        return base
    ks = sorted(sh)
    if slot <= ks[0]: f = sh[ks[0]]
    elif slot >= ks[-1]: f = sh[ks[-1]]
    else:
        i = next(j for j, x in enumerate(ks) if x >= slot)
        x0, x1 = ks[i - 1], ks[i]; f = sh[x0] + (sh[x1] - sh[x0]) * (slot - x0) / (x1 - x0)
    return base * f


# ---------- レポート(依存なしのHTML+SVG) ----------
SERIES = ["#2a78d6", "#eb6834", "#1baf7a", "#eda100", "#e87ba4", "#008300"]
SERIES_D = ["#3987e5", "#d95926", "#199e70", "#c98500", "#d55181", "#0ca30c"]
OTHER = "#9a9890"


def report(park, rides, daily_ci, slot_ci, model, queue, top, occ):
    hm = lambda m: f"{m // 60}:{m % 60:02d}"
    W, H, L, B, T = 760, 300, 48, 34, 16
    # 1) 日ごとの混雑指数(棒)
    ds = list(daily_ci)
    mx = max(150, max(daily_ci.values()) * 1.1) if ds else 150
    bw = (W - L - 10) / max(1, len(ds))
    bars = []
    for i, d in enumerate(ds):
        v = daily_ci[d]; h = (H - B - T) * v / mx; x = L + i * bw
        wd = "月火水木金土日"[date.fromisoformat(d).weekday()]
        bars.append(f'<rect class="m" x="{x + 1:.1f}" y="{H - B - h:.1f}" width="{max(1, bw - 2):.1f}" height="{h:.1f}" rx="2" fill="var(--s1)" data-tip="{d}({wd}) 混雑指数 {v:.0f}"/>')
        if len(ds) <= 31 or i % 3 == 0:
            bars.append(f'<text x="{x + bw / 2:.1f}" y="{H - B + 14}" class="ax" text-anchor="middle">{d[5:].replace("-", "/")}</text>')
    y100 = H - B - (H - B - T) * 100 / mx
    grid = "".join(f'<line x1="{L}" x2="{W - 10}" y1="{H - B - (H - B - T) * g / mx:.1f}" y2="{H - B - (H - B - T) * g / mx:.1f}" class="gr"/><text x="{L - 6}" y="{H - B - (H - B - T) * g / mx + 4:.1f}" class="ax" text-anchor="end">{g}</text>' for g in range(0, int(mx) + 1, 50))
    chart1 = f'<svg viewBox="0 0 {W} {H}" role="img" aria-label="日ごとの混雑指数">{grid}{"".join(bars)}<line x1="{L}" x2="{W - 10}" y1="{y100:.1f}" y2="{y100:.1f}" class="ref"/><text x="{W - 12}" y="{T + 2}" class="ax" text-anchor="end">点線 = 平均(100)</text></svg>'

    # 2) 時間帯ごとの列の人数(積み上げ面)
    slots = sorted(queue)
    if slots:
        tot = {s: sum(queue[s].values()) for s in slots}
        ymax = max(tot.values()) * 1.1 or 1
        x0, x1 = slots[0], slots[-1]
        X = lambda s: L + (W - L - 10) * (s - x0) / max(1, x1 - x0)
        Y = lambda v: H - B - (H - B - T) * v / ymax
        keys = top + ["other"]
        acc = {s: 0.0 for s in slots}; layers = []
        for i, k in enumerate(keys):
            lo = dict(acc)
            for s in slots:
                acc[s] += queue[s].get(k, 0) if k != "other" else sum(v for kk, v in queue[s].items() if kk not in top)
            pts = " ".join(f"{X(s):.1f},{Y(acc[s]):.1f}" for s in slots) + " " + " ".join(f"{X(s):.1f},{Y(lo[s]):.1f}" for s in reversed(slots))
            col = f"var(--s{i + 1})" if k != "other" else "var(--oth)"
            layers.append(f'<polygon points="{pts}" fill="{col}" stroke="var(--bg)" stroke-width="1.5"/>')
        step = 10 ** max(0, len(str(int(ymax))) - 1)
        step = step if ymax / step >= 3 else step // 2 or 1
        g2 = "".join(f'<line x1="{L}" x2="{W - 10}" y1="{Y(g):.1f}" y2="{Y(g):.1f}" class="gr"/><text x="{L - 6}" y="{Y(g) + 4:.1f}" class="ax" text-anchor="end">{g:,}</text>' for g in range(0, int(ymax) + 1, step))
        xt = "".join(f'<text x="{X(s):.1f}" y="{H - B + 14}" class="ax" text-anchor="middle">{s // 60}時</text>' for s in slots if s % 120 == 0)
        chart2 = f'<svg viewBox="0 0 {W} {H}" id="c2" role="img" aria-label="時間帯ごとの列の人数">{g2}{"".join(layers)}{xt}<line id="xh" y1="{T}" y2="{H - B}" class="xh" style="display:none"/></svg>'
        legend = "".join(f'<span><i style="background:var(--s{i + 1})"></i>{k}. {rides[k]["name"]}</span>' for i, k in enumerate(top)) + '<span><i style="background:var(--oth)"></i>その他</span>'
        qdata = json.dumps({"x0": x0, "x1": x1, "L": L, "W": W, "slots": slots, "rows": [[round(tot[s])] + [round(queue[s].get(k, 0)) for k in top] for s in slots], "names": [rides[k]["name"] for k in top]}, ensure_ascii=False)
    else:
        chart2, legend, qdata = "<p>データ不足</p>", "", "null"

    # 3) 表:アトラクションの反応
    rows = sorted(model.items(), key=lambda kv: -(kv[1]["a"] + kv[1]["b"] * 100))
    trs = "".join(f'<tr><td>{k}</td><td>{rides[k]["name"]}</td><td class="n">{max(0, m["a"] + m["b"] * 80):.0f}</td><td class="n">{max(0, m["a"] + m["b"] * 100):.0f}</td><td class="n">{max(0, m["a"] + m["b"] * 120):.0f}</td><td class="n">{m["b"] * 10:+.1f}</td><td class="n">{m["r2"]:.2f}</td><td class="n">{m["days"]}</td></tr>' for k, m in rows)

    occ_rows = sorted(occ.items(), key=lambda kv: -kv[1][0])[:20]
    omax = max([v for _, (t, bl) in occ_rows for v in bl] + [0.01])
    cell = lambda v: f'<td class="n" style="background:color-mix(in oklab, var(--s1) {min(85, v / omax * 85):.0f}%, var(--bg))">{v * 100:.0f}</td>'
    otr = "".join(f'<tr><td>{k}. {rides[k]["name"]}</td><td class="n"><b>{t:.1%}</b></td>' + "".join(cell(v) for v in bl) + "</tr>" for k, (t, bl) in occ_rows)
    occ_html = f'<div class="wrap"><table><tr><th>アトラクション</th><th class="n">1日</th>' + "".join(f'<th class="n">{b}時〜</th>' for b in (8, 10, 12, 14, 16, 18, 20, 22)) + f'</tr>{otr}</table></div>'
    css = """:root{color-scheme:light dark;--bg:light-dark(#fcfcfb,#1a1a19);--ink:light-dark(#0b0b0b,#f0efec);--sub:light-dark(#52514e,#c3c2b7);--gr:light-dark(#e6e5e0,#33332f);--oth:#9a9890;""" + \
          "".join(f"--s{i + 1}:light-dark({a},{b});" for i, (a, b) in enumerate(zip(SERIES, SERIES_D))) + """}
body{margin:0;background:var(--bg);color:var(--ink);font:15px/1.55 system-ui,"Hiragino Sans","Noto Sans JP",sans-serif}
main{max-width:860px;margin:auto;padding:24px 16px 48px}h1{font-size:26px;margin:0 0 4px}h2{font-size:18px;margin:32px 0 4px}p.s{color:var(--sub);margin:0 0 10px}
svg{width:100%;height:auto;display:block}.gr{stroke:var(--gr)}.ref{stroke:var(--sub);stroke-dasharray:4 4}.ax{fill:var(--sub);font-size:11px}.xh{stroke:var(--sub)}
.lg{display:flex;flex-wrap:wrap;gap:6px 14px;font-size:13px;color:var(--sub);margin:6px 0}.lg i{display:inline-block;width:11px;height:11px;border-radius:3px;margin-right:5px;vertical-align:-1px}
table{border-collapse:collapse;width:100%;font-size:13px}th,td{padding:6px 8px;border-bottom:1px solid var(--gr);text-align:left}td.n,th.n{text-align:right;font-variant-numeric:tabular-nums}.wrap{overflow-x:auto}
#tip{position:fixed;pointer-events:none;background:var(--ink);color:var(--bg);font-size:12px;padding:6px 8px;border-radius:6px;display:none;white-space:pre;z-index:9}
.m:hover{opacity:.8}.foot{font-size:12px;color:var(--sub);margin-top:24px}"""
    js = """<script>{const tip=document.getElementById('tip');const show=(e,t)=>{tip.textContent=t;tip.style.display='block';tip.style.left=Math.min(innerWidth-220,e.clientX+12)+'px';tip.style.top=(e.clientY+12)+'px'};
document.querySelectorAll('[data-tip]').forEach(el=>{el.addEventListener('pointermove',e=>show(e,el.dataset.tip));el.addEventListener('pointerleave',()=>tip.style.display='none')});
const Q=""" + qdata + """;const c2=document.getElementById('c2');if(Q&&c2){const xh=document.getElementById('xh');
c2.addEventListener('pointermove',e=>{const r=c2.getBoundingClientRect();const vx=(e.clientX-r.left)*Q.W/r.width;const s=Q.x0+(vx-Q.L)/(Q.W-Q.L-10)*(Q.x1-Q.x0);
let i=0,best=1e9;Q.slots.forEach((x,j)=>{if(Math.abs(x-s)<best){best=Math.abs(x-s);i=j}});const sl=Q.slots[i],px=Q.L+(Q.W-Q.L-10)*(sl-Q.x0)/Math.max(1,Q.x1-Q.x0);
xh.setAttribute('x1',px);xh.setAttribute('x2',px);xh.style.display='';const row=Q.rows[i];
show(e,`${Math.floor(sl/60)}:${String(sl%60).padStart(2,'0')}  列の合計 約${row[0].toLocaleString()}人\\n`+Q.names.map((n,j)=>`${n}  ${row[j+1].toLocaleString()}人`).join('\\n'))});
c2.addEventListener('pointerleave',()=>{tip.style.display='none';xh.style.display='none'})}}</script>"""
    html = f"""<!DOCTYPE html><html lang="ja"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>{park} 混雑レポート</title><style>{css}</style></head><body><main>
<h1>{park} 混雑レポート</h1><p class="s">{min(daily_ci)}〜{max(daily_ci)}の{len(daily_ci)}日分。混雑指数100 = データ期間の平均的な混み具合。</p>
<h2>日ごとの混雑指数</h2><p class="s">人気アトラクションの平均待ち時間を、期間平均に対する%で表したもの。</p>{chart1}
<h2>時間帯ごとの、列に並んでいる人数(推定)</h2><p class="s">列の人数 ≒ 1時間あたりの処理人数 ÷ 60 × 待ち時間。混雑指数100の日を想定。列以外(食事・買い物・移動中)の人は含まない。</p>
<div class="lg">{legend}</div>{chart2}
<h2>アトラクションごとのゲスト占有率</h2><p class="s">列に並んでいる人全体のうち、そのアトラクションの列にいる人の割合(%)。時間帯ごとの数字が大きいほど、その時間にゲストがそこへ集まっている。色が濃いほど高い。上位20件(全件は models/{park}_share.csv)。</p>{occ_html}
<h2>混雑指数に対する各アトラクションの反応</h2><p class="s">1日の平均待ち時間(分)。「指数+10あたり」は混雑指数が10上がると平均待ちが何分増えるか。R²は当てはまりの良さ(1に近いほど指数で説明できる)。</p>
<div class="wrap"><table><tr><th>番号</th><th>アトラクション</th><th class="n">指数80</th><th class="n">指数100</th><th class="n">指数120</th><th class="n">指数+10あたり</th><th class="n">R²</th><th class="n">日数</th></tr>{trs}</table></div>
<p class="foot">処理人数は公表値ではなく推定の目安(rides.json の capacity_per_hour で直せます)。表示待ち時間は実際より長めに出ることが多いので、列の人数は傾向を見るための目安です。Powered by <a href="https://queue-times.com/">Queue-Times.com</a></p>
</main><div id="tip"></div>{js}</body></html>"""
    return html


def main():
    ap = argparse.ArgumentParser(); ap.add_argument("--park", choices=["DL", "DCA"], required=True)
    ap.add_argument("--backtest", action="store_true", help="予測の精度を検証する")
    a = ap.parse_args()
    if a.backtest:
        backtest(a.park); return
    rides, days, daily_ci, slot_ci, model = build(a.park)
    os.makedirs("models", exist_ok=True)
    # 混雑指数100の日の、時間帯ごとの列の人数
    slots = sorted({int(s) for m in model.values() for s in m["shape"]})
    queue = {s: {k: rides[k]["capacity_per_hour"] / 60 * predict(m, s, 100) for k, m in model.items() if str(s) in m["shape"]} for s in slots}
    share = defaultdict(float)
    for s in slots:
        for k, v in queue[s].items(): share[k] += v
    top = [k for k, _ in sorted(share.items(), key=lambda kv: -kv[1])[:6]]

    json.dump({"park": a.park, "daily_ci": daily_ci, "slot_ci": slot_ci, "rides": model}, open(f"models/{a.park}.json", "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    with open(f"models/{a.park}_daily.csv", "w", newline="", encoding="utf-8-sig") as f:
        w = csv.writer(f); w.writerow(["日付", "曜日", "混雑指数"])
        for d, v in daily_ci.items(): w.writerow([d, "月火水木金土日"[date.fromisoformat(d).weekday()], round(v)])
    with open(f"models/{a.park}_rides.csv", "w", newline="", encoding="utf-8-sig") as f:
        w = csv.writer(f); w.writerow(["番号", "アトラクション", "指数80の平均待ち", "指数100", "指数120", "指数+10あたりの増加(分)", "R2", "日数"])
        for k, m in sorted(model.items(), key=lambda kv: -(kv[1]["a"] + kv[1]["b"] * 100)):
            w.writerow([k, rides[k]["name"], round(max(0, m["a"] + m["b"] * 80)), round(max(0, m["a"] + m["b"] * 100)), round(max(0, m["a"] + m["b"] * 120)), round(m["b"] * 10, 1), round(m["r2"], 2), m["days"]])
    total_all = sum(share.values()) or 1
    blocks = [(8, 10), (10, 12), (12, 14), (14, 16), (16, 18), (18, 20), (20, 22), (22, 24)]
    def bshare(k, b0, b1):
        ss = [s for s in slots if b0 * 60 <= s < b1 * 60]
        tot = sum(sum(queue[s].values()) for s in ss)
        return sum(queue[s].get(k, 0) for s in ss) / tot if tot else 0
    with open(f"models/{a.park}_share.csv", "w", newline="", encoding="utf-8-sig") as f:
        w = csv.writer(f)
        w.writerow(["番号", "アトラクション", "1日の占有率"] + [f"{b0}〜{b1}時" for b0, b1 in blocks])
        for k in sorted(model, key=lambda k: -share[k]):
            w.writerow([k, rides[k]["name"], f"{share[k] / total_all:.1%}"] + [f"{bshare(k, b0, b1):.1%}" for b0, b1 in blocks])
    occ = {k: (share[k] / total_all, [bshare(k, b0, b1) for b0, b1 in blocks]) for k in model}
    with open(f"models/{a.park}_queue.csv", "w", newline="", encoding="utf-8-sig") as f:
        w = csv.writer(f); keys = sorted(model, key=lambda k: -share[k])
        w.writerow(["時刻", "列の合計(人)"] + [f'{k}.{rides[k]["name"]}' for k in keys])
        for s in slots: w.writerow([f"{s // 60}:{s % 60:02d}", round(sum(queue[s].values()))] + [round(queue[s].get(k, 0)) for k in keys])
    open(f"models/{a.park}_report.html", "w", encoding="utf-8").write(report(a.park, rides, daily_ci, slot_ci, model, queue, top, occ))
    print(f"{a.park}: {len(daily_ci)}日分で混雑指数モデルを作りました → models/")
    lo = min(daily_ci, key=daily_ci.get); hi = max(daily_ci, key=daily_ci.get)
    print(f"  いちばん空いていた日 {lo}(指数{daily_ci[lo]:.0f}) / いちばん混んでいた日 {hi}(指数{daily_ci[hi]:.0f})")
    print(f"  列の人数が多い上位: " + "、".join(rides[k]["name"] for k in top[:3]))


if __name__ == "__main__":
    main()
