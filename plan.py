"""貯めた待ち時間の傾向(profiles/<park>.json)から、1日の最適な回り方を計算する。

使い方:
  python plan.py plan_DL.json

やっていること:
  ・各アトラクションの「その時刻の待ち時間」をデータから引く(データがなければ推定値)
  ・徒歩時間は rides.json の座標(おおよそ、単位m)から計算
  ・ショー(時刻固定)・食事(時間帯の中で好きな時刻)・パス(マルチパスの予約ルール)を入れる
  ・「待ち+徒歩」の合計が短く、優先度の高いものが多く入る順番を焼きなまし法で探す
  ・時間内に入りきらないものは、優先度の低いものから「省略候補」に回す
"""
import argparse, json, math, random, sys
from bisect import bisect_left

WALK_M_PER_MIN = 70.0   # 歩く速さ
DETOUR = 1.35           # 直線距離→実際の道のりの補正


def tmin(s):
    h, m = s.split(":"); return int(h) * 60 + int(m)


def hm(t):
    t = int(round(t)); return f"{t // 60}:{t % 60:02d}"


def season_mult(t):
    """データがないアトラクション用の時間帯係数(推定)"""
    h = t / 60
    return 0.25 if h < 8.5 else 0.4 if h < 9.5 else 0.65 if h < 10.5 else 0.85 if h < 11.5 else 1.0 if h < 17 else 0.85 if h < 19 else 0.7


class ModelWaits:
    """model.py の混雑指数モデルで待ち時間を予測する"""
    def __init__(self, model, rides, ci):
        from model import predict
        self.m, self.rides, self.ci, self.pred = model.get("rides", {}), rides, ci, predict

    def at(self, num, t):
        if num in self.m and self.m[num]["shape"]:
            return self.pred(self.m[num], t, self.ci)
        return self.rides[num]["fallback_peak"] * season_mult(t) * self.ci / 100

    def has(self, num): return num in self.m


class GbmWaits:
    """gbm.py の勾配ブースティングで待ち時間を予測する(15分枠ごとに先にまとめて計算しておく)"""
    def __init__(self, bundle, rides, cfg):
        import pandas as pd
        from datetime import date
        from warehouse import us_holidays
        d = date.fromisoformat(cfg["date"])
        entry, close = tmin(cfg["entry"]), tmin(cfg["exit"])
        key = "C" if cfg.get("crowd_index") is not None else "D"
        m, feats, cats = bundle["models"][key], bundle["features"][key], bundle["categories"]
        shows = [(tmin(s["start"]) - 30, tmin(s["end"])) for s in cfg.get("shows", [])]
        known = set(cats["ride"])
        self.rides, self.p = rides, {}
        nums = [n for n in rides if n in known]
        slots = list(range(entry // 15 * 15, close + 15, 15))
        rows = [{"ride": n, "slot": s, "since_open": s - entry, "hours_est": (close - entry) / 60, "dow": d.isoweekday(),
                 "is_weekend": int(d.isoweekday() >= 6), "is_holiday": int(d in us_holidays([d.year])),
                 "holiday_season": int(d.month == 12 or (d.month == 11 and d.day >= 14) or (d.month == 1 and d.day <= 7)),
                 "weather": cfg.get("weather", ""), "event": cfg.get("event", ""), "show_on": int(any(a <= s < b for a, b in shows)),
                 "month_day": d.timetuple().tm_yday, "crowd_index": cfg.get("crowd_index")} for n in nums for s in slots]
        X = pd.DataFrame(rows)
        for c in ("ride", "weather", "event"):
            X[c] = pd.Categorical(X[c], categories=cats[c])
        y = m.predict(X[feats]).clip(0)
        for (n, s), v in zip(((r["ride"], r["slot"]) for r in rows), y):
            self.p.setdefault(n, {})[s] = float(v)
        self.label = f"勾配ブースティング({'混雑指数 ' + str(cfg['crowd_index']) if key == 'C' else '混雑指数なし'}、{cfg['date']}、天気: {cfg.get('weather') or '指定なし'})"

    def at(self, num, t):
        if num in self.p:
            s = int(t) // 15 * 15
            sl = self.p[num]
            return sl.get(s, sl[min(sl, key=lambda x: abs(x - s))])
        return self.rides[num]["fallback_peak"] * season_mult(t)

    def has(self, num): return num in self.p


class Waits:
    def __init__(self, profile, rides):
        self.rides = rides
        self.p = {}
        for num, slots in profile.get("rides", {}).items():
            xs = sorted((int(s), v["median"]) for s, v in slots.items() if v["n"] >= 1)
            if xs:
                self.p[num] = ([x for x, _ in xs], [y for _, y in xs])

    def at(self, num, t):
        if num in self.p:
            xs, ys = self.p[num]
            i = bisect_left(xs, t)
            if i == 0: return ys[0]
            if i >= len(xs): return ys[-1]
            x0, x1, y0, y1 = xs[i - 1], xs[i], ys[i - 1], ys[i]
            return y0 + (y1 - y0) * (t - x0) / (x1 - x0)
        return self.rides[num]["fallback_peak"] * season_mult(t)

    def has(self, num): return num in self.p


def want_list(cfg):
    """乗りたいアトラクション。"want" があればそれ、なければ旧形式の3つのリストを合わせたもの"""
    if "want" in cfg:
        return [str(n) for n in cfg["want"]]
    out = []
    for key in ("multi_pass", "standby", "single_pass"):
        for n in cfg.get(key, []):
            if str(n) not in out:
                out.append(str(n))
    return out


def priorities(cfg, rides):
    pr = {str(k): v for k, v in cfg.get("priority", {}).items()}
    sp = {str(n) for n in cfg.get("single_pass", [])}
    return {k: pr.get(k, 5 if k in sp else 3) for k in want_list(cfg)}


def avg_standby(W, k, cfg):
    """パスを使える時間帯(入園〜ll_use_until)のスタンバイ予測の平均"""
    a, b = tmin(cfg["entry"]), tmin(cfg.get("ll_use_until", cfg["exit"]))
    ts = list(range(a, max(a + 15, b), 15))
    return sum(W.at(k, t) for t in ts) / len(ts)


def ll_candidates(cfg, rides, W):
    """マルチパスの候補を優先順位の順に並べる。
    戻り値: (候補の番号リスト, {番号: 候補から外した理由})"""
    want, pr = want_list(cfg), priorities(cfg, rides)
    sp = {str(n) for n in cfg.get("single_pass", [])}
    elig = [k for k in want if rides[k].get("lightning_lane") == "multi" and k not in sp]
    out = {}
    if not cfg.get("use_multi_pass", True):
        return [], {k: "マルチパスを使わない設定" for k in elig}
    skip = {str(n) for n in cfg.get("ll_skip", [])}
    order = [str(n) for n in cfg.get("ll_priority", [])]
    rest = sorted((k for k in elig if k not in order),
                  key=lambda k: (-pr[k], rides[k].get("ll_demand") != "high", -avg_standby(W, k, cfg)))
    cands = []
    for k in [k for k in order if k in elig] + rest:
        if k in skip:
            out[k] = "取らない指定(ll_skip)"
        elif k not in order and avg_standby(W, k, cfg) < cfg.get("ll_min_standby", 30):
            out[k] = f"スタンバイで十分(日中の平均 {round(avg_standby(W, k, cfg))}分)"
        else:
            cands.append(k)
    return cands, out


def build(cfg, rides, cands):
    """並べ替える項目を作る。
    ・パス候補は優先順位の順に予約する(どれを取るかは最適化しない)。並べ替えるのは「n番目のパスを使う」タイミングだけ
    ・パス候補にもスタンバイの項目を入れておく(戻り時刻が上限に入らず取れなかったときや、朝いちばんに乗るとき用)"""
    items, val = [], {}
    pr = priorities(cfg, rides)
    sp = {str(n) for n in cfg.get("single_pass", [])}
    for k in want_list(cfg):
        val[("R", k)] = pr[k]
        items.append(("SP", k) if k in sp else ("SB", k))
    for i in range(len(cands)):
        items.append(("LL", str(i)))
    for i, s in enumerate(cfg.get("shows", [])):
        items.append(("SH", str(i))); val[("SH", str(i))] = s.get("priority", 4)
    for i, m in enumerate(cfg.get("meals", [])):
        items.append(("ML", str(i))); val[("ML", str(i))] = 20
    return items, val


def ll_return(cfg, k, r, book, start):
    """戻り時刻の見込み(バッファ込み)。[取った時刻から何分後, 入園からの経過分×係数] + ll_buffer_min"""
    d = cfg.get("ll_delay_override", {}).get(k) or \
        (cfg.get("ll_delay_high", [60, 0.25]) if r.get("ll_demand") == "high" else cfg.get("ll_delay_mid", [30, 0.10]))
    s = cfg.get("_ll_scale", 1.0)
    return book + (d[0] + d[1] * (book - start)) * s + cfg.get("ll_buffer_min", 15)


def simulate(order, cfg, rides, W, val, cands, ret=False):
    start, close = tmin(cfg["entry"]), tmin(cfg["exit"])
    until = min(close, tmin(cfg.get("ll_use_until", cfg["exit"])))
    llq = cfg.get("ll_queue_min", 10)                        # パスの列で並ぶ時間
    x, y, t, pen = 0.0, 0.0, float(start), 0.0
    book, done, log, qi, note = float(start), set(), [], 0, {}
    for it in order:
        kind, k = it
        if kind == "ML":
            m = cfg["meals"][int(k)]; a, b = tmin(m["from"]), tmin(m["to"])
            if t > b: pen += val[it] * 1000; continue
            t = max(t, a); log.append((it, 0, t, 0, m["minutes"], None)); t += m["minutes"]; continue
        if kind == "SH":
            s = cfg["shows"][int(k)]
            nr = rides.get(str(s.get("near")), {}); sx, sy = (nr["x"], nr["y"]) if nr else (s.get("x", 0), s.get("y", 0))
            w = math.hypot(sx - x, sy - y) * DETOUR / WALK_M_PER_MIN
            arrive = tmin(s["start"]) - s.get("arrive_before", 30)
            if t + w > arrive: pen += val[it] * 1000; continue
            log.append((it, w, arrive, 0, tmin(s["end"]) - arrive, None)); t = tmin(s["end"]); x, y = sx, sy; continue
        if kind == "LL":
            # 次に予約するもの = 候補のうち、まだ乗っておらず、戻り時刻が上限に入るもので最も優先順位が高いもの
            while qi < len(cands):
                k = cands[qi]; r = rides[k]; qi += 1
                if k in done: note[k] = "パスを取る前にスタンバイで乗る"; continue
                rt = ll_return(cfg, k, r, book, start)
                if rt + llq + r["ride_min"] > until:
                    note[k] = f"戻り時刻が {cfg.get('ll_use_until', cfg['exit'])} までに入らない"; continue
                break
            else:
                continue
            w = math.hypot(r["x"] - x, r["y"] - y) * DETOUR / WALK_M_PER_MIN; ta = t + w
            st_ = max(ta, rt)
            if st_ > rt + 60 - cfg.get("ll_buffer_min", 15) or st_ + llq + r["ride_min"] > until:
                pen += val[("R", k)] * 300                   # 枠に間に合わない=パスを無駄にした
                note[k] = "予約したが枠に間に合わない"; book = book + 120; continue
            pen += (st_ - ta) * 2                            # 戻り時刻まで手持ち無沙汰の待ちは減点
            log.append((("LL", k), w, st_, llq, r["ride_min"], (book, rt))); done.add(k)
            book = min(st_, book + 120)                      # 使ったら次を取る/取ってから2時間で次を取れる
            t = st_ + llq + r["ride_min"]; x, y = r["x"], r["y"]; continue
        if k in done: continue                                # パスで乗った
        r = rides[k]; w = math.hypot(r["x"] - x, r["y"] - y) * DETOUR / WALK_M_PER_MIN; ta = t + w
        if kind == "SP":
            st_ = max(ta, start + 60); fin = st_ + llq + r["ride_min"]
            if fin > close: continue
            log.append((it, w, st_, llq, r["ride_min"], None)); done.add(k); t = fin; x, y = r["x"], r["y"]; continue
        if k in cands[qi:] and ll_return(cfg, k, r, book, start) + llq + r["ride_min"] <= until:
            continue                                         # まだパスで乗れる見込みがあるものはスタンバイにしない
        wait = W.at(k, ta)
        if ta + wait + r["ride_min"] > close: continue
        log.append((it, w, ta, wait, r["ride_min"], None)); done.add(k); t = ta + wait + r["ride_min"]; x, y = r["x"], r["y"]
    pen += sum(v * 1000 for (kind, k), v in val.items() if kind == "R" and k not in done)
    if ret: return t, log, done, note
    return pen + t * 0.5


def optimize(cfg, rides, W, cands, iters=150000, restarts=6, seed=1):
    items, val = build(cfg, rides, cands)
    best = None
    for s in range(restarts):
        rnd = random.Random(seed + s); cur = items[:]; rnd.shuffle(cur)
        cs = simulate(cur, cfg, rides, W, val, cands); T = 500.0; loc = (cs, cur[:])
        for _ in range(iters):
            a, b = sorted(rnd.sample(range(len(cur)), 2)); c = cur[:]; r = rnd.random()
            if r < .4: c[a], c[b] = c[b], c[a]
            elif r < .7: c[a:b + 1] = reversed(c[a:b + 1])
            else: c.insert(b, c.pop(a))
            sc = simulate(c, cfg, rides, W, val, cands)
            if sc < cs or rnd.random() < math.exp((cs - sc) / T): cur, cs = c, sc
            if cs < loc[0]: loc = (cs, cur[:])
            T = max(.05, T * 0.99995)
        if best is None or loc[0] < best[0]: best = loc
    return best[1], val


def make_waits(cfg, rides, park):
    if cfg.get("wait_model") == "gbm":
        import joblib
        try:
            W = GbmWaits(joblib.load(f"models/{park}_gbm.joblib"), rides, cfg)
        except FileNotFoundError:
            raise SystemExit("models/ に学習済みモデルがありません。先に python gbm.py --park " + park + " を実行してください")
        return W, {"model": W.label}
    if cfg.get("crowd_index") is not None:
        try:
            W = ModelWaits(json.load(open(f"models/{park}.json", encoding="utf-8")), rides, float(cfg["crowd_index"]))
        except FileNotFoundError:
            raise SystemExit("models/ がありません。先に python model.py --park " + park + " を実行してください")
        return W, {"model": f"混雑指数 {cfg['crowd_index']} の日を想定(model.py)"}
    profile = {"rides": {}, "meta": {}}
    try:
        profile = json.load(open(cfg.get("profile", f"profiles/{park}.json"), encoding="utf-8"))
    except FileNotFoundError:
        print("※ profiles がまだないので、全部推定値で計算します(analyze.py を先に実行すると実データになります)")
    return Waits(profile, rides), profile.get("meta", {})


def run(cfg, rides, W, iters):
    cands, excluded = ll_candidates(cfg, rides, W)
    order, val = optimize(cfg, rides, W, cands, iters=iters)
    end, log, done, note = simulate(order, cfg, rides, W, val, cands, ret=True)
    return {"cands": cands, "excluded": excluded, "val": val, "end": end, "log": log, "done": done, "note": note,
            "method": {l[0][1]: l[0][0] for l in log if l[0][0] in ("LL", "SB", "SP")},
            "wait": sum(l[3] for l in log), "walk": sum(l[1] for l in log),
            "shows": [l[0] for l in log if l[0][0] == "SH"]}


def hmin(m):
    m = int(m); return f"{m // 60}時間{m % 60}分"


def main():
    ap = argparse.ArgumentParser(description="1日の回り方を最適化する(マルチパスは優先順位どおりに取る)")
    ap.add_argument("config", nargs="?", default="plan_DL.json")
    ap.add_argument("--fast", action="store_true", help="反復を1/10にして素早く試す(結果は粗くなる)")
    ap.add_argument("--robust", action="store_true", help="戻り時刻の見込みを0.5倍・1.5倍にしたとき、取れるパスが変わるか確かめる")
    ap.add_argument("--no-compare", action="store_true", help="「マルチパスなし」との比較を省く")
    a = ap.parse_args()
    cfg = json.load(open(a.config, encoding="utf-8"))
    park = cfg["park"]
    rides = json.load(open("rides.json", encoding="utf-8"))[park]
    W, meta = make_waits(cfg, rides, park)
    iters = cfg.get("iterations", 150000) // (10 if a.fast else 1)
    use_ll = cfg.get("use_multi_pass", True)
    want = want_list(cfg)
    pr = priorities(cfg, rides)
    llq = cfg.get("ll_queue_min", 10)
    until = cfg.get("ll_use_until", cfg["exit"])

    print("計算中: メインのプラン …", flush=True)
    R = run(cfg, rides, W, iters)

    def label(it):
        kind, k = it
        if kind == "SH": return "🎆 " + cfg["shows"][int(k)]["name"], ""
        if kind == "ML": return "🍴 " + cfg["meals"][int(k)]["name"], ""
        if kind == "SB":
            tag = "スタンバイ(パス対象)" if use_ll and rides[k].get("lightning_lane") == "multi" else "スタンバイ"
            return f"{k}. {rides[k]['name']}", f"{tag}・{'実データ' if W.has(k) else '推定'}"
        return f"{k}. {rides[k]['name']}", {"LL": "マルチパス", "SP": "シングルパス"}[kind]

    lines = [f"# {park} 回り方プラン(入園{cfg['entry']}・退園{cfg['exit']})", ""]
    if meta.get("model"): lines.append("待ち時間: " + meta["model"])
    elif meta.get("from"): lines.append(f"待ち時間データ: {meta.get('from')}〜{meta.get('to')}の{meta.get('days_used')}日分({meta.get('filter')})")
    else: lines.append("待ち時間: データがまだないため全部推定値")
    if use_ll:
        lines += ["", f"マルチパス: 優先順位の高いものから順に予約する。パスで乗り終えるのは {until} まで。"
                      f"戻り時刻は見込みより {cfg.get('ll_buffer_min', 15)}分遅れる前提。"
                      f"日中のスタンバイ平均が {cfg.get('ll_min_standby', 30)}分未満のものは取らない"]
    lines += ["", "| 時刻 | やること | 種類 | 待ち | 徒歩 | 備考 |", "|---|---|---|---|---|---|"]
    for it, w, t, wait, dur, ex in R["log"]:
        name, tag = label(it)
        if it[0] == "LL": note = f"{hm(ex[0])}にパスを取る(戻り{hm(ex[1])}〜)"
        elif it[0] in ("SH", "ML"): note = f"〜{hm(t + dur)}"
        else: note = ""
        lines.append(f"| {hm(t)} | {name} | {tag} | {round(wait)}分 | {round(w)}分 | {note} |")
    skipped = [("R", k) for k in want if k not in R["done"]] + \
              [("SH", str(i)) for i in range(len(cfg.get("shows", []))) if ("SH", str(i)) not in R["shows"]]
    lines += ["", f"- 回れる数: アトラクション{len(R['done'])}個 + ショー{len(R['shows'])}つ",
              f"- 待ち時間の合計: {hmin(R['wait'])} / 歩く時間の合計: {int(R['walk'])}分 / 最後の予定が終わる時刻: {hm(R['end'])}"]
    if skipped:
        lines += ["", "## 時間内に入らなかったもの(省略候補)"]
        for it in sorted(skipped, key=lambda i: R["val"][i]):
            nm = f"{it[1]}. {rides[it[1]]['name']}" if it[0] == "R" else label(it)[0]
            lines.append(f"- {nm}(優先度 {R['val'][it]})")

    elig = [k for k in want if rides[k].get("lightning_lane") == "multi" and k not in {str(n) for n in cfg.get("single_pass", [])}]
    if use_ll and elig:
        used = {l[0][1]: l for l in R["log"] if l[0][0] == "LL"}
        sb_at = {l[0][1]: l for l in R["log"] if l[0][0] == "SB"}
        lines += ["", "## マルチパスの取り方(優先順位の順)", "",
                  "| 順位 | アトラクション | 優先度 | 人気 | 判定 | 予約する時刻 | 戻り時刻(見込み) | 乗る時刻 | その時刻のスタンバイ予測 |",
                  "|---|---|---|---|---|---|---|---|---|"]
        rank = {k: i + 1 for i, k in enumerate(R["cands"])}
        for k in R["cands"] + [k for k in elig if k not in R["cands"]]:
            r = rides[k]; pop = "高" if r.get("ll_demand") == "high" else "中"
            head = f"| {rank.get(k, '-')} | {k}. {r['name']} | {pr[k]} | {pop} | "
            if k in used:
                _, _, t, _, _, (bk, rt) = used[k]
                lines.append(head + f"**取る** | {hm(bk)} | {hm(rt)}〜 | {hm(t)} | {round(W.at(k, t))}分 |")
            else:
                why = R["excluded"].get(k) or R["note"].get(k) or "予約の順番が回ってこない"
                sb = f"スタンバイ {hm(sb_at[k][2])}({round(sb_at[k][3])}分)" if k in sb_at else "乗らない"
                lines.append(head + f"取らない:{why} | - | - | {sb} | - |")
        lines += ["", "次の予約は「パスを使った後」か「予約から2時間後」の早い方からできます。表の予約時刻は、その最も早い時刻です。",
                  f"取る順番を自分で決めたいときは `ll_priority` に番号を並べ、取らないものは `ll_skip` に入れます。"]

    if use_ll and elig and not a.no_compare:
        print("計算中: マルチパスを使わない場合 …", flush=True)
        N = run({**cfg, "use_multi_pass": False}, rides, W, iters)
        miss = lambda X: ", ".join(k for k in want if k not in X["done"]) or "なし"
        lines += ["", "## マルチパスを使わない場合との比較", "", "| | マルチパスあり | マルチパスなし |", "|---|---|---|",
                  f"| 乗れるアトラクション | {len(R['done'])}個 | {len(N['done'])}個 |",
                  f"| 見られるショー | {len(R['shows'])}つ | {len(N['shows'])}つ |",
                  f"| 待ち時間の合計 | {hmin(R['wait'])} | {hmin(N['wait'])} |",
                  f"| 最後の予定が終わる時刻 | {hm(R['end'])} | {hm(N['end'])} |",
                  f"| 乗れないもの(番号) | {miss(R)} | {miss(N)} |"]

    if use_ll and elig and a.robust:
        alt = {}
        for s in (0.5, 1.5):
            print(f"計算中: 戻り時刻の見込み×{s} …", flush=True)
            alt[s] = run({**cfg, "_ll_scale": s}, rides, W, iters)["method"]
        name = {"LL": "パス", "SB": "スタンバイ", None: "乗らない"}
        lines += ["", "## 戻り時刻の見込みがずれた場合(--robust)", "",
                  "| アトラクション | 見込み×0.5(早く戻れる) | 見込みどおり | 見込み×1.5(遅く戻る) | 判定 |", "|---|---|---|---|---|"]
        for k in R["cands"]:
            ms = [alt[0.5].get(k), R["method"].get(k), alt[1.5].get(k)]
            lines.append(f"| {k}. {rides[k]['name']} | " + " | ".join(name[m] for m in ms) + f" | {'変わらない' if len(set(ms)) == 1 else '**見込み次第**'} |")
        lines += ["", "「見込み次第」のものは、当日アプリで実際の戻り時刻を見てから決めてください。"]

    lines += ["", "## 注意",
              "- マルチパスの戻り時刻はAPIから取れないため、`ll_delay_*` の見込み値にバッファ(`ll_buffer_min`)を足して計算しています。当日アプリに出る時刻に合わせて数字を直すと、計算し直せます",
              "- スタンバイの待ち時間は表示値がもとで、実際より長めに出やすいです",
              "", "Powered by [Queue-Times.com](https://queue-times.com/)"]
    out = f"plan_{park}.md"
    open(out, "w", encoding="utf-8").write("\n".join(lines))
    print("\n".join(lines)); print(f"\n→ {out} に保存しました")


if __name__ == "__main__":
    main()
