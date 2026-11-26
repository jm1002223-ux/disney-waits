"""待ち時間データの分析。

  python insights.py --park DL

1. クラスタリング … 待ち時間の傾向が似たアトラクションをグループに分ける
   特徴量:平均待ちの大きさ / 時間帯ごとの形(2時間ごと)/ 朝の伸び / 混雑への反応 / 日ごとのぶれ / 止まりやすさ
   k-means(k-means++、50回やり直し)で、グループ数はシルエット係数が最大になる数を選ぶ。
   精度の確認として、日をランダムに選び直して(ブートストラップ50回)同じ分け方になるかを
   調整ランド指数(ARI)で測り、アトラクションごとの「所属の確からしさ」も出す。
2. 朝いちばんの価値 … 開園直後に乗ると、昼間に乗るより何分得するか
   (昼11〜17時の平均待ち − 開園30分の平均待ち)× 開園時に動いている確率
   全体の順位と、グループ内の順位を出す。
3. システム調整(シス調) … 営業中に「運営中」でなくなった回数・時間・時間帯
   1日に1回以上止まる確率、平均の停止時間、時間帯ごとの止まっている確率、開園時に動いていない確率。

出力: insights/<park>_clusters.csv, <park>_ropedrop.csv, <park>_downtime.csv, <park>_report.html
Powered by Queue-Times.com (https://queue-times.com/)
"""
import argparse, csv, glob, json, math, os, random
from collections import defaultdict, Counter
from datetime import datetime
from zoneinfo import ZoneInfo

import cleaning

TZ = ZoneInfo("America/Los_Angeles")
SLOT = 15
# 分析に使わない記録(現地0〜5時・閉園後)の決まりは cleaning.py
BLOCKS = [(8, 10), (10, 12), (12, 14), (14, 16), (16, 18), (18, 20), (20, 22), (22, 24)]


def mean(x): return sum(x) / len(x) if x else 0.0


def std(x):
    m = mean(x); return math.sqrt(mean([(v - m) ** 2 for v in x])) if len(x) > 1 else 0.0


# ---------------- データ読み込み ----------------
def load(park):
    rides = json.load(open("rides.json", encoding="utf-8"))[park]
    by_qid = {str(v["queue_times_id"]): k for k, v in rides.items()}
    keep = cleaning.keeper(park)
    W = defaultdict(lambda: defaultdict(dict))   # ride -> day -> slot -> 待ち(営業中のみ)
    O = defaultdict(lambda: defaultdict(dict))   # ride -> day -> slot -> 1/0(運営中か)
    seen = set()
    for path in sorted(glob.glob(os.path.join("data", park, "*.csv"))):
        with open(path, newline="", encoding="utf-8") as f:
            for r in csv.DictReader(f):
                k = by_qid.get(r["ride_id"])
                if not k:
                    continue
                ts = datetime.fromisoformat(r["fetched_utc"].replace("Z", "+00:00")).astimezone(TZ)
                if not keep(ts):
                    continue
                key = (k, r["fetched_utc"])
                if key in seen:
                    continue
                seen.add(key)
                d, s = ts.date().isoformat(), (ts.hour * 60 + ts.minute) // SLOT * SLOT
                op = r["is_open"] == "1"
                O[k][d][s] = max(O[k][d].get(s, 0), int(op))
                if op:
                    W[k][d][s] = float(r["wait_time"] or 0)
    if not O:
        raise SystemExit(f"data/{park}/ にデータがありません")
    days = sorted({d for r in O.values() for d in r})
    # その日のパークの営業時間帯:半分以上のアトラクションが動いている時間帯
    hours = {}
    for d in days:
        cnt = Counter(); tot = Counter()
        for k in O:
            for s, v in O[k].get(d, {}).items():
                tot[s] += 1; cnt[s] += v
        op = sorted(s for s in tot if cnt[s] >= tot[s] * 0.5)
        if op:
            hours[d] = (op[0], op[-1])
    return rides, W, O, days, hours


# ---------------- シス調 ----------------
def downtime(rides, O, days, hours):
    res = {}
    for k in O:
        events, durs, per_hour_down, per_hour_tot = [], [], Counter(), Counter()
        days_obs = days_with = morning_obs = morning_down = 0
        for d in days:
            if d not in hours or d not in O[k]:
                continue
            o, (h0, h1) = O[k][d], hours[d]
            sl = sorted(s for s in o if h0 <= s <= h1)
            opened = [s for s in sl if o[s]]
            if not opened:
                continue                              # その日は終日運休(改修など)→数えない
            days_obs += 1
            morning_obs += 1
            if not o.get(h0, 0) and not o.get(h0 + SLOT, 0):
                morning_down += 1                     # 開園30分のあいだ動いていない
            first, last = opened[0], opened[-1]
            had, cur = False, None
            for s in sl:
                if s < first or s > last:
                    continue
                per_hour_tot[s // 60] += 1
                if not o[s]:
                    per_hour_down[s // 60] += 1
                    if cur is None:
                        cur = s
                elif cur is not None:
                    events.append(cur); durs.append(s - cur); cur = None; had = True
            days_with += had
        if days_obs:
            res[k] = {"days": days_obs, "p_day": days_with / days_obs, "events_per_day": len(events) / days_obs,
                      "avg_min": mean(durs), "p_morning_down": morning_down / morning_obs if morning_obs else 0,
                      "start_hours": Counter(e // 60 for e in events),
                      "p_hour": {h: per_hour_down[h] / per_hour_tot[h] for h in per_hour_tot if per_hour_tot[h]}}
    return res


# ---------------- 特徴量 ----------------
def ride_features(k, W, dsel, hours, dt):
    """dsel:使う日のリスト(重複あり=ブートストラップ)"""
    vals = [w for d in dsel for w in W[k].get(d, {}).values()]
    if len(vals) < 8:
        return None
    m = mean(vals) or 0.1
    shape = []
    for a, b in BLOCKS:
        v = [w for d in dsel for s, w in W[k].get(d, {}).items() if a * 60 <= s < b * 60]
        shape.append(mean(v) / m if v else 1.0)
    # 朝の伸び:開園から2時間の待ちの増え方(分/時)
    gr = []
    for d in dsel:
        if d not in hours:
            continue
        h0 = hours[d][0]; sl = W[k].get(d, {})
        e = [sl[s] for s in sl if h0 <= s < h0 + 30]; l = [sl[s] for s in sl if h0 + 90 <= s < h0 + 150]
        if e and l:
            gr.append((mean(l) - mean(e)) / 2)
    daily = [mean(list(W[k][d].values())) for d in dsel if W[k].get(d)]
    cv = std(daily) / (mean(daily) or 1)
    # 混雑への反応:その日の全体の混み具合に対する、このアトラクションの弾力性
    return {"level": math.log1p(m), "shape": shape, "growth": mean(gr) / (m or 1) if gr else 0.0, "cv": cv,
            "down": dt.get(k, {}).get("events_per_day", 0.0), "mean": m}


def elasticity(W, dsel, keys):
    """各アトラクションの日平均を、全体の混雑指数で回帰した傾き÷平均(=混雑に対する反応の強さ)"""
    allm = {k: mean([w for d in dsel for w in W[k].get(d, {}).values()]) or 1 for k in keys}
    ci = {}
    for d in set(dsel):
        r = [mean(list(W[k][d].values())) / allm[k] for k in keys if W[k].get(d)]
        if r:
            ci[d] = mean(r)
    out = {}
    for k in keys:
        xs = [ci[d] for d in dsel if d in ci and W[k].get(d)]
        ys = [mean(list(W[k][d].values())) / allm[k] for d in dsel if d in ci and W[k].get(d)]
        if len(xs) >= 3 and std(xs) > 1e-9:
            mx, my = mean(xs), mean(ys)
            out[k] = sum((x - mx) * (y - my) for x, y in zip(xs, ys)) / sum((x - mx) ** 2 for x in xs)
        else:
            out[k] = 1.0
    return out


def matrix(W, dsel, hours, dt, keys):
    F = {k: ride_features(k, W, dsel, hours, dt) for k in keys}
    keys = [k for k in keys if F[k]]
    el = elasticity(W, dsel, keys)
    X = [[F[k]["level"] * 2.0] + [v * 1.0 for v in F[k]["shape"]] + [F[k]["growth"] * 1.5, el[k], F[k]["cv"], F[k]["down"]] for k in keys]
    # 標準化
    cols = list(zip(*X)); mu = [mean(c) for c in cols]; sd = [std(c) or 1 for c in cols]
    Z = [[(x - m) / s for x, m, s in zip(row, mu, sd)] for row in X]
    return keys, Z, F, el


# ---------------- k-means / 評価 ----------------
def d2(a, b): return sum((x - y) ** 2 for x, y in zip(a, b))


def kmeans(Z, k, rnd, restarts=50, iters=100):
    best = None
    for _ in range(restarts):
        C = [Z[rnd.randrange(len(Z))]]
        while len(C) < k:                              # k-means++
            ds = [min(d2(z, c) for c in C) for z in Z]; t = rnd.random() * sum(ds); acc = 0
            for z, dd in zip(Z, ds):
                acc += dd
                if acc >= t:
                    C.append(z); break
        lab = [0] * len(Z)
        for _ in range(iters):
            new = [min(range(k), key=lambda j: d2(z, C[j])) for z in Z]
            if new == lab and _:
                break
            lab = new
            for j in range(k):
                mem = [z for z, l in zip(Z, lab) if l == j]
                if mem:
                    C[j] = [mean(c) for c in zip(*mem)]
        sse = sum(d2(z, C[l]) for z, l in zip(Z, lab))
        if best is None or sse < best[0]:
            best = (sse, lab, C)
    return best[1], best[2]


def silhouette(Z, lab):
    n = len(Z); s = []
    for i in range(n):
        same = [math.sqrt(d2(Z[i], Z[j])) for j in range(n) if j != i and lab[j] == lab[i]]
        if not same:
            s.append(0); continue
        a = mean(same)
        b = min(mean([math.sqrt(d2(Z[i], Z[j])) for j in range(n) if lab[j] == c]) for c in set(lab) if c != lab[i])
        s.append((b - a) / max(a, b) if max(a, b) > 0 else 0)
    return mean(s), s


def ari(a, b):
    n = len(a)
    if n < 2:
        return 1.0
    c2 = lambda x: x * (x - 1) / 2
    ct = Counter(zip(a, b)); sa = sum(c2(v) for v in Counter(a).values()); sb = sum(c2(v) for v in Counter(b).values())
    idx = sum(c2(v) for v in ct.values()); exp = sa * sb / c2(n); mx = (sa + sb) / 2
    return (idx - exp) / (mx - exp) if mx != exp else 1.0


def name_cluster(members, F, el):
    lv = mean([F[k]["mean"] for k in members]); gr = mean([F[k]["growth"] for k in members])
    sh = [mean(v) for v in zip(*[F[k]["shape"] for k in members])]
    peak = BLOCKS[max(range(len(sh)), key=lambda i: sh[i])]
    night = sh[-2] + sh[-1] > sh[2] + sh[3]
    size = "人気・長い列" if lv >= 45 else "中くらいの列" if lv >= 20 else "列が短め"
    feat = "朝から急に伸びる" if gr > 0.25 and lv >= 20 else ("夜も混む" if night else f"{peak[0]}〜{peak[1]}時がピーク")
    return f"{size}/{feat}"


# ---------------- 朝いちばんの価値 ----------------
def ropedrop(W, O, days, hours, dt, keys):
    out = {}
    for k in keys:
        early, mid = [], []
        for d in days:
            if d not in hours:
                continue
            h0 = hours[d][0]; sl = W[k].get(d, {})
            early += [sl[s] for s in sl if h0 <= s < h0 + 30]
            mid += [sl[s] for s in sl if 11 * 60 <= s < 17 * 60]
        if not early or not mid:
            continue
        p_open = 1 - dt.get(k, {}).get("p_morning_down", 0)
        out[k] = {"early": mean(early), "mid": mean(mid), "saved": (mean(mid) - mean(early)) * p_open, "p_open": p_open}
    return out


# ---------------- レポート ----------------
CSS = """:root{color-scheme:light dark;--bg:light-dark(#fcfcfb,#1a1a19);--ink:light-dark(#0b0b0b,#f0efec);--sub:light-dark(#52514e,#c3c2b7);--gr:light-dark(#e6e5e0,#33332f);--s1:light-dark(#2a78d6,#3987e5)}
body{margin:0;background:var(--bg);color:var(--ink);font:15px/1.55 system-ui,"Hiragino Sans","Noto Sans JP",sans-serif}
main{max-width:900px;margin:auto;padding:24px 16px 48px}h1{font-size:26px;margin:0 0 4px}h2{font-size:19px;margin:34px 0 4px}h3{font-size:15px;margin:18px 0 4px}p.s{color:var(--sub);margin:0 0 10px}
table{border-collapse:collapse;width:100%;font-size:13px}th,td{padding:6px 8px;border-bottom:1px solid var(--gr);text-align:left;vertical-align:top}.n{text-align:right;font-variant-numeric:tabular-nums}.wrap{overflow-x:auto}
td:last-child{white-space:nowrap}.bar{display:inline-block;height:10px;border-radius:0 3px 3px 0;background:var(--s1);vertical-align:middle;margin-right:6px}
.hm td.c{width:34px;height:22px;padding:0;text-align:center;font-size:11px;color:var(--ink)}.kpi{display:flex;gap:10px;flex-wrap:wrap;margin:8px 0}.kpi div{border:1px solid var(--gr);border-radius:10px;padding:8px 12px}.kpi b{font-size:20px;display:block}
.foot{font-size:12px;color:var(--sub);margin-top:24px}"""


def heat(p):
    """0→背景、1→濃い青(単色の濃淡)"""
    a = min(1.0, p / 0.25)   # 25%で最大の濃さ
    return f"background:color-mix(in oklab, var(--s1) {a * 85:.0f}%, var(--bg))"


def main():
    ap = argparse.ArgumentParser(); ap.add_argument("--park", choices=["DL", "DCA"], required=True)
    ap.add_argument("--boot", type=int, default=50); ap.add_argument("--seed", type=int, default=1)
    a = ap.parse_args(); rnd = random.Random(a.seed)
    rides, W, O, days, hours = load(a.park)
    if len(days) < 5:
        raise SystemExit(f"分析には5日分以上のデータが必要です(今は{len(days)}日分)")
    dt = downtime(rides, O, days, hours)
    keys, Z, F, el = matrix(W, days, hours, dt, [k for k in rides if k in W])

    # グループ数の決定(シルエット係数が最大)
    scores = {}
    for k in range(2, min(8, len(keys) - 1) + 1):
        lab, _ = kmeans(Z, k, rnd, restarts=30)
        scores[k] = (silhouette(Z, lab)[0], lab)
    K = max(scores, key=lambda k: scores[k][0]); sil, base = scores[K][0], scores[K][1]
    sil_each = silhouette(Z, base)[1]

    # ブートストラップで安定性
    aris, co = [], defaultdict(list)
    for _ in range(a.boot):
        ds = [rnd.choice(days) for _ in days]
        kb, Zb, _, _ = matrix(W, ds, hours, dt, keys)
        if kb != keys:
            continue
        lb, _ = kmeans(Zb, K, rnd, restarts=10)
        aris.append(ari(base, lb))
        for i, k in enumerate(keys):
            mates = [j for j in range(len(keys)) if j != i and base[j] == base[i]]
            if mates:
                co[k].append(mean([1.0 if lb[j] == lb[i] else 0.0 for j in mates]))
    stab = mean(aris)

    groups = defaultdict(list)
    for k, l in zip(keys, base):
        groups[l].append(k)
    rd = ropedrop(W, O, days, hours, dt, keys)
    gname = {l: name_cluster(m, F, el) for l, m in groups.items()}
    order = sorted(groups, key=lambda l: -mean([F[k]["mean"] for k in groups[l]]))
    gid = {l: i + 1 for i, l in enumerate(order)}

    os.makedirs("insights", exist_ok=True)
    with open(f"insights/{a.park}_clusters.csv", "w", newline="", encoding="utf-8-sig") as f:
        w = csv.writer(f); w.writerow(["グループ", "グループの特徴", "番号", "アトラクション", "平均待ち(分)", "所属の確からしさ", "シルエット"])
        for l in order:
            for k in sorted(groups[l], key=lambda k: -F[k]["mean"]):
                w.writerow([gid[l], gname[l], k, rides[k]["name"], round(F[k]["mean"]), round(mean(co[k]), 2) if co[k] else "", round(sil_each[keys.index(k)], 2)])
    rank = sorted(rd, key=lambda k: -rd[k]["saved"])
    with open(f"insights/{a.park}_ropedrop.csv", "w", newline="", encoding="utf-8-sig") as f:
        w = csv.writer(f); w.writerow(["全体順位", "グループ", "グループ内順位", "番号", "アトラクション", "開園30分の平均待ち", "11〜17時の平均待ち", "開園時に動いている確率", "朝に乗ると得する時間(分)"])
        inner = {}
        for k in rank:
            g = gid[base[keys.index(k)]]; inner[g] = inner.get(g, 0) + 1
            w.writerow([rank.index(k) + 1, g, inner[g], k, rides[k]["name"], round(rd[k]["early"]), round(rd[k]["mid"]), f"{rd[k]['p_open']:.0%}", round(rd[k]["saved"])])
    with open(f"insights/{a.park}_downtime.csv", "w", newline="", encoding="utf-8-sig") as f:
        w = csv.writer(f); w.writerow(["番号", "アトラクション", "1日に1回以上止まる確率", "1日あたりの回数", "平均の停止時間(分)", "開園時に動いていない確率", "止まり始めが多い時間帯", "日数"])
        for k in sorted(dt, key=lambda k: -dt[k]["p_day"]):
            v = dt[k]; top = "、".join(f"{h}時台" for h, _ in v["start_hours"].most_common(3))
            w.writerow([k, rides[k]["name"], f"{v['p_day']:.0%}", round(v["events_per_day"], 2), round(v["avg_min"]), f"{v['p_morning_down']:.0%}", top, v["days"]])

    # ダッシュボード(export_dashboard.py)用の要約。計算は上のCSVと同じ
    json.dump({
        "park": a.park, "days": len(days), "k": K, "silhouette": round(sil, 3), "ari": round(stab, 3), "boot_used": len(aris),
        "k_scores": {str(k): round(v[0], 3) for k, v in scores.items()},
        "groups": [{"id": gid[l], "name": gname[l], "members": [
            {"no": k, "name": rides[k]["name"], "mean": round(F[k]["mean"], 1), "confidence": round(mean(co[k]), 2) if co[k] else None,
             "silhouette": round(sil_each[keys.index(k)], 2)} for k in sorted(groups[l], key=lambda k: -F[k]["mean"])]} for l in order],
        "ropedrop": [{"rank": i + 1, "group": gid[base[keys.index(k)]], "no": k, "name": rides[k]["name"], "early": round(rd[k]["early"], 1),
                      "mid": round(rd[k]["mid"], 1), "p_open": round(rd[k]["p_open"], 3), "saved": round(rd[k]["saved"], 1)} for i, k in enumerate(rank)],
        "downtime": [{"no": k, "name": rides[k]["name"], "p_day": round(v["p_day"], 3), "events_per_day": round(v["events_per_day"], 2),
                      "avg_min": round(v["avg_min"], 1), "p_morning_down": round(v["p_morning_down"], 3), "days": v["days"],
                      "start_hours": {str(h): n for h, n in v["start_hours"].items()},
                      "p_hour": {str(h): round(p, 3) for h, p in v["p_hour"].items()}} for k, v in sorted(dt.items(), key=lambda kv: -kv[1]["p_day"])],
    }, open(f"insights/{a.park}_summary.json", "w", encoding="utf-8"), ensure_ascii=False, indent=1)

    # HTML
    verdict ="安定(同じデータの取り方なら、ほぼ同じ分け方になる)" if stab >= 0.75 else "やや不安定(データが増えると変わる可能性あり)" if stab >= 0.5 else "不安定(データ不足。日数が増えてから見直す)"
    gsec = ""
    for l in order:
        rows = "".join(f'<tr><td class="n">{k}</td><td>{rides[k]["name"]}</td><td class="n">{F[k]["mean"]:.0f}</td><td class="n">{(mean(co[k]) if co[k] else 0):.0%}</td></tr>' for k in sorted(groups[l], key=lambda k: -F[k]["mean"]))
        gsec += f'<h3>グループ{gid[l]}:{gname[l]}({len(groups[l])})</h3><div class="wrap"><table><tr><th class="n">番号</th><th>アトラクション</th><th class="n">平均待ち(分)</th><th class="n">所属の確からしさ</th></tr>{rows}</table></div>'
    mx = max([rd[k]["saved"] for k in rank] + [1])
    inner = {}; rrows = ""
    for i, k in enumerate(rank):
        g = gid[base[keys.index(k)]]; inner[g] = inner.get(g, 0) + 1
        rrows += f'<tr><td class="n">{i + 1}</td><td>{k}. {rides[k]["name"]}</td><td class="n">G{g}-{inner[g]}</td><td class="n">{rd[k]["early"]:.0f}</td><td class="n">{rd[k]["mid"]:.0f}</td><td class="n">{rd[k]["p_open"]:.0%}</td><td><span class="bar" style="width:{max(0, rd[k]["saved"]) / mx * 140:.0f}px"></span>{rd[k]["saved"]:.0f}分</td></tr>'
    hrs = sorted({h for v in dt.values() for h in v["p_hour"]})
    dk = sorted([k for k in dt if dt[k]["p_day"] > 0], key=lambda k: -dt[k]["p_day"])[:20]
    hm = "".join(f'<tr><td>{k}. {rides[k]["name"]}</td><td class="n">{dt[k]["p_day"]:.0%}</td><td class="n">{dt[k]["avg_min"]:.0f}</td><td class="n">{dt[k]["p_morning_down"]:.0%}</td>' + "".join(f'<td class="c" style="{heat(dt[k]["p_hour"].get(h, 0))}" title="{h}時台 {dt[k]["p_hour"].get(h, 0):.0%}">{round(dt[k]["p_hour"].get(h, 0) * 100) or ""}</td>' for h in hrs) + "</tr>" for k in dk)
    html = f"""<!DOCTYPE html><html lang="ja"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>{a.park} 分析レポート</title><style>{CSS}</style></head><body><main>
<h1>{a.park} 分析レポート</h1><p class="s">{days[0]}〜{days[-1]}の{len(days)}日分</p>
<h2>1. アトラクションのグループ分け</h2><p class="s">平均待ちの大きさ・時間帯ごとの形・朝の伸び・混雑への反応・日ごとのぶれ・止まりやすさで、似たもの同士をk-meansで分類。</p>
<div class="kpi"><div>グループ数<b>{K}</b></div><div>シルエット係数<b>{sil:.2f}</b></div><div>安定性(ARI)<b>{stab:.2f}</b></div></div>
<p class="s">シルエット係数:グループの分かれ方のはっきりさ(0.5以上ではっきり、0.25未満はあいまい)。安定性:日を選び直して{len(aris)}回分類し直したときに同じ分け方になる度合い(1が完全一致)→ {verdict}。所属の確からしさ:そのアトラクションが、選び直しても同じ仲間と同じグループに入った割合。</p>
{gsec}
<h2>2. 朝いちばんに乗る価値</h2><p class="s">開園直後に乗ると、昼(11〜17時)に乗るより何分得するか。開園時に止まっていることが多いものは、その分割り引いています。「G2-1」はグループ2の中で1位の意味。</p>
<div class="wrap"><table><tr><th class="n">順位</th><th>アトラクション</th><th class="n">グループ内</th><th class="n">開園30分の待ち</th><th class="n">昼の待ち</th><th class="n">開園時に動いている</th><th>得する時間</th></tr>{rrows}</table></div>
<h2>3. システム調整(シス調)</h2><p class="s">営業中に「運営中」でなくなった記録から。マスの数字は、その時間帯に止まっていた割合(%)。色が濃いほど止まりやすい(25%以上で最も濃い)。止まりやすい上位20件。</p>
<div class="wrap"><table class="hm"><tr><th>アトラクション</th><th class="n">1日に1回以上</th><th class="n">平均停止(分)</th><th class="n">開園時に停止</th>{"".join(f'<th class="n" style="font-size:11px">{h}</th>' for h in hrs)}</tr>{hm}</table></div>
<p class="foot">5分おきの記録なので、5分未満の停止は見逃すことがあります(実行が遅れた時間帯はもっと粗くなります)。終日運休の日(改修など)はシス調に数えていません。待ち時間は表示値です。Powered by <a href="https://queue-times.com/">Queue-Times.com</a></p>
</main></body></html>"""
    open(f"insights/{a.park}_report.html", "w", encoding="utf-8").write(html)
    print(f"{a.park}: {len(days)}日分を分析しました → insights/")
    print(f"  グループ数 {K}(シルエット係数 {sil:.2f}、安定性ARI {stab:.2f}:{verdict})")
    print("  朝いちばんの価値 上位5: " + "、".join(f"{rides[k]['name']}({rd[k]['saved']:.0f}分)" for k in rank[:5]))
    top = sorted(dt, key=lambda k: -dt[k]["p_day"])[:3]
    print("  止まりやすい上位3: " + "、".join(f"{rides[k]['name']}({dt[k]['p_day']:.0%})" for k in top))


if __name__ == "__main__":
    main()
