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
import json, math, random, sys
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


def build(cfg, rides):
    items, val = [], {}
    pr = {str(k): v for k, v in cfg.get("priority", {}).items()}
    for n in cfg.get("standby", []):
        items.append(("SB", str(n))); val[("SB", str(n))] = pr.get(str(n), 3)
    for n in cfg.get("multi_pass", []):
        items.append(("LL", str(n))); val[("LL", str(n))] = pr.get(str(n), 3)
        if cfg.get("allow_standby_fallback", True):
            items.append(("SBX", str(n))); val[("SBX", str(n))] = 0
    for n in cfg.get("single_pass", []):
        items.append(("SP", str(n))); val[("SP", str(n))] = pr.get(str(n), 5)
    for i, s in enumerate(cfg.get("shows", [])):
        items.append(("SH", str(i))); val[("SH", str(i))] = s.get("priority", 4)
    for i, m in enumerate(cfg.get("meals", [])):
        items.append(("ML", str(i))); val[("ML", str(i))] = 20
    return items, val


def simulate(order, cfg, rides, W, val, ret=False):
    start, close = tmin(cfg["entry"]), tmin(cfg["exit"])
    hi = cfg.get("ll_delay_high", [60, 0.25]); mid = cfg.get("ll_delay_mid", [30, 0.10])
    x, y, t, pen = 0.0, 0.0, float(start), 0.0
    book, done, log = float(start), set(), []
    multi = [str(n) for n in cfg.get("multi_pass", [])]
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
        if k in done: continue
        r = rides[k]; w = math.hypot(r["x"] - x, r["y"] - y) * DETOUR / WALK_M_PER_MIN; ta = t + w
        if kind == "LL":
            d = hi if r.get("ll_demand") == "high" else mid
            rt = book + d[0] + d[1] * (book - start)
            if ta > rt + 60: pen += 3000; continue          # 戻り時刻の1時間枠に間に合わない
            st_ = max(ta, rt); fin = st_ + 10 + r["ride_min"]
            if fin > close: continue
            pen += (st_ - ta) * 2                            # 手持ち無沙汰の待ちは減点
            log.append((it, w, st_, 10, r["ride_min"], book)); done.add(k)
            book = min(st_, book + 120)                      # 使ったら次を取る/2時間ルール
            t = fin; x, y = r["x"], r["y"]; continue
        if kind == "SP":
            st_ = max(ta, start + 60); fin = st_ + 10 + r["ride_min"]
            if fin > close: pen += val[it] * 1000; continue
            log.append((it, w, st_, 10, r["ride_min"], None)); done.add(k); t = fin; x, y = r["x"], r["y"]; continue
        wait = W.at(k, ta)
        if ta + wait + r["ride_min"] > close:
            if kind != "SBX": pen += val[it] * 1000
            continue
        log.append((it, w, ta, wait, r["ride_min"], None)); done.add(k); t = ta + wait + r["ride_min"]; x, y = r["x"], r["y"]
    pen += sum(val[("LL", k)] * 1000 for k in multi if k not in done)
    if ret: return t, log, done
    return pen + t * 0.5


def optimize(cfg, rides, W, iters=150000, restarts=6, seed=1):
    items, val = build(cfg, rides)
    best = None
    for s in range(restarts):
        rnd = random.Random(seed + s); cur = items[:]; rnd.shuffle(cur)
        cs = simulate(cur, cfg, rides, W, val); T = 500.0; loc = (cs, cur[:])
        for _ in range(iters):
            a, b = sorted(rnd.sample(range(len(cur)), 2)); c = cur[:]; r = rnd.random()
            if r < .4: c[a], c[b] = c[b], c[a]
            elif r < .7: c[a:b + 1] = reversed(c[a:b + 1])
            else: c.insert(b, c.pop(a))
            sc = simulate(c, cfg, rides, W, val)
            if sc < cs or rnd.random() < math.exp((cs - sc) / T): cur, cs = c, sc
            if cs < loc[0]: loc = (cs, cur[:])
            T = max(.05, T * 0.99995)
        if best is None or loc[0] < best[0]: best = loc
    return best[1], val


def main():
    cfg = json.load(open(sys.argv[1] if len(sys.argv) > 1 else "plan_DL.json", encoding="utf-8"))
    park = cfg["park"]
    rides = json.load(open("rides.json", encoding="utf-8"))[park]
    profile = {"rides": {}, "meta": {}}
    if cfg.get("wait_model") == "gbm":
        import joblib
        try:
            W = GbmWaits(joblib.load(f"models/{park}_gbm.joblib"), rides, cfg)
        except FileNotFoundError:
            raise SystemExit("models/ に学習済みモデルがありません。先に python gbm.py --park " + park + " を実行してください")
        profile["meta"] = {"model": W.label}
    elif cfg.get("crowd_index") is not None:
        try:
            W = ModelWaits(json.load(open(f"models/{park}.json", encoding="utf-8")), rides, float(cfg["crowd_index"]))
            profile["meta"] = {"model": f"混雑指数 {cfg['crowd_index']} の日を想定(model.py)"}
        except FileNotFoundError:
            raise SystemExit("models/ がありません。先に python model.py --park " + park + " を実行してください")
    else:
        try:
            profile = json.load(open(cfg.get("profile", f"profiles/{park}.json"), encoding="utf-8"))
        except FileNotFoundError:
            print("※ profiles がまだないので、全部推定値で計算します(analyze.py を先に実行すると実データになります)")
        W = Waits(profile, rides)
    order, val = optimize(cfg, rides, W, iters=cfg.get("iterations", 150000))
    end, log, done = simulate(order, cfg, rides, W, val, ret=True)

    def label(it):
        kind, k = it
        if kind == "SH": return "🎆 " + cfg["shows"][int(k)]["name"], ""
        if kind == "ML": return "🍴 " + cfg["meals"][int(k)]["name"], ""
        tag = {"LL": "マルチパス", "SP": "シングルパス", "SBX": "通常(パス対象)", "SB": "通常"}[kind]
        src = "" if kind in ("LL", "SP") else ("実データ" if W.has(k) else "推定")
        return f"{k}. {rides[k]['name']}", f"{tag}" + (f"・{src}" if src else "")

    lines = [f"# {park} 回り方プラン(入園{cfg['entry']}・退園{cfg['exit']})", ""]
    meta = profile.get("meta", {})
    if meta.get("model"): lines.append("待ち時間: " + meta["model"])
    elif meta: lines.append(f"待ち時間データ: {meta.get('from')}〜{meta.get('to')}の{meta.get('days_used')}日分({meta.get('filter')})")
    lines += ["", "| 時刻 | やること | 種類 | 待ち | 徒歩 | 備考 |", "|---|---|---|---|---|---|"]
    tw = tk = 0
    for it, w, t, wait, dur, book in log:
        name, tag = label(it)
        note = f"{hm(book)}にパスを取る" if book is not None else (f"〜{hm(t + dur)}" if it[0] in ("SH", "ML") else "")
        lines.append(f"| {hm(t)} | {name} | {tag} | {round(wait)}分 | {round(w)}分 | {note} |")
        tw += wait; tk += w
    skipped = [it for it in order if it[0] in ("SB", "LL", "SP", "SH") and not ((it[0] in ("SB", "LL", "SP") and it[1] in done) or (it[0] == "SH" and any(l[0] == it for l in log)))]
    lines += ["", f"- 回れる数: アトラクション{len(done)}個 + ショー{sum(1 for l in log if l[0][0]=='SH')}つ",
              f"- 待ち時間の合計: {int(tw)//60}時間{int(tw)%60}分 / 歩く時間の合計: {int(tk)}分 / 最後の予定が終わる時刻: {hm(end)}"]
    if skipped:
        lines += ["", "## 時間内に入らなかったもの(省略候補)"]
        for it in sorted(skipped, key=lambda i: val[i]):
            lines.append(f"- {label(it)[0]}(優先度 {val[it]})")
    lines += ["", "Powered by [Queue-Times.com](https://queue-times.com/)"]
    out = f"plan_{park}.md"
    open(out, "w", encoding="utf-8").write("\n".join(lines))
    print("\n".join(lines)); print(f"\n→ {out} に保存しました")


if __name__ == "__main__":
    main()
