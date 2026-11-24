"""ダッシュボード用の集計値を dashboard/data/<park>.json に書き出す。

  python warehouse.py          # 先にデータベースを作り直す
  python export_dashboard.py   # → dashboard/data/DL.json, DCA.json

書き出すのは集計値だけ(生データの行は入れない)。
Powered by Queue-Times.com (https://queue-times.com/)
"""
import json, os, sys
from datetime import datetime
from zoneinfo import ZoneInfo

import duckdb

DB = "warehouse/disney.duckdb"
OUT = os.path.join("dashboard", "data")
PARK_NAME = {"DL": "ディズニーランド・パーク", "DCA": "ディズニー・カリフォルニア・アドベンチャー"}
WEEKDAY = {"Monday": "月", "Tuesday": "火", "Wednesday": "水", "Thursday": "木", "Friday": "金", "Saturday": "土", "Sunday": "日"}


def rows(con, sql, *params):
    cur = con.execute(sql, params)
    cols = [d[0] for d in cur.description]
    return [dict(zip(cols, r)) for r in cur.fetchall()]


def r1(x, nd=1):
    return None if x is None else round(float(x), nd)


def hm(m):
    return f"{int(m) // 60}:{int(m) % 60:02d}"


def export(con, park):
    rng = con.execute("""SELECT count(*), count(DISTINCT date_local), min(date_local), max(date_local), max(ts_local)
                         FROM fact_waits WHERE park = ?""", [park]).fetchone()
    if not rng[0]:
        return None

    # 日ごと:営業時間(推定)・混雑指数・取得回数と充足率・実行間隔
    days = rows(con, """
        WITH runs AS (
            SELECT f.date_local, f.ts_local FROM fact_waits f WHERE f.park = ? GROUP BY ALL),
        win AS (
            SELECT c.*, CAST(split_part(c.open_est, ':', 1) AS INT) * 60 + CAST(split_part(c.open_est, ':', 2) AS INT) AS o
            FROM dim_calendar c WHERE c.park = ?),
        r AS (
            SELECT w.date_local, r.ts_local,
                   date_diff('minute', lag(r.ts_local) OVER (PARTITION BY w.date_local ORDER BY r.ts_local), r.ts_local) AS gap
            FROM win w JOIN runs r USING (date_local)
            WHERE hour(r.ts_local) * 60 + minute(r.ts_local) >= w.o AND hour(r.ts_local) * 60 + minute(r.ts_local) < w.o + w.hours_est * 60)
        SELECT w.date_local, w.weekday, w.is_weekend, w.holiday, w.event, w.open_est, w.close_est, w.hours_est, w.crowd_index,
               count(r.ts_local) AS runs, median(r.gap) AS median_gap, max(r.gap) AS max_gap,
               count(DISTINCT (hour(r.ts_local) * 60 + minute(r.ts_local)) // 15) AS slots
        FROM win w LEFT JOIN r USING (date_local) GROUP BY ALL ORDER BY w.date_local""", park, park)
    for d in days:
        # 充足率は分析計画書の定義:営業時間(推定)の15分枠のうち、記録がある割合
        exp_slots = (d["hours_est"] or 0) * 60 / 15
        d["expected"] = int(round(exp_slots))
        d["coverage"] = r1(min(1.0, d["slots"] / exp_slots) if exp_slots else None, 3)

    # アトラクションごとの指標
    base = {r["ride_no"]: r for r in rows(con, """
        SELECT d.ride_no, d.name, d.lightning_lane, d.ll_demand,
               avg(f.wait_time) AS avg_wait, max(f.wait_time) AS max_wait
        FROM dim_ride d LEFT JOIN fact_waits f ON f.park = d.park AND f.ride_no = d.ride_no
        WHERE d.park = ? GROUP BY ALL HAVING count(f.wait_time) > 0""", park)}
    uptime = {r["ride_no"]: r["u"] for r in rows(con, "SELECT ride_no, avg(uptime) AS u FROM v_daily_ride WHERE park = ? GROUP BY ALL", park)}
    downs = {r["ride_no"]: r for r in rows(con, """
        SELECT ride_no, count(*) AS n, sum(date_diff('minute', down_from, coalesce(up_again, down_from))) AS minutes
        FROM v_downtime_events WHERE park = ? GROUP BY ALL""", park)}
    prof = {}
    for r in rows(con, """
        SELECT f.ride_no, f.slot15, CASE WHEN c.is_weekend THEN 'weekend' ELSE 'weekday' END AS kind,
               median(f.wait_time) AS med, quantile_cont(f.wait_time, 0.9) AS p90, count(*) AS n
        FROM fact_waits f JOIN dim_calendar c USING (park, date_local)
        WHERE f.park = ? AND f.wait_time IS NOT NULL GROUP BY ALL
        UNION ALL
        SELECT ride_no, slot15, 'all', median(wait_time), quantile_cont(wait_time, 0.9), count(*)
        FROM fact_waits WHERE park = ? AND wait_time IS NOT NULL GROUP BY ALL""", park, park):
        prof.setdefault(r["ride_no"], {}).setdefault(r["kind"], []).append([r["slot15"], r1(r["med"]), r1(r["p90"]), r["n"]])
    hourly = {}
    for r in rows(con, """SELECT ride_no, hour_local, median(wait_time) AS med FROM fact_waits
                          WHERE park = ? AND wait_time IS NOT NULL GROUP BY ALL""", park):
        hourly.setdefault(r["ride_no"], []).append([r["hour_local"], r1(r["med"])])
    latest = {r["ride_no"]: r for r in rows(con, """
        SELECT ride_no, is_open, wait_time, ts_local FROM fact_waits
        WHERE park = ? AND ride_no IS NOT NULL QUALIFY row_number() OVER (PARTITION BY ride_no ORDER BY ts_local DESC) = 1""", park)}

    rides = []
    for no, b in base.items():
        p = {k: sorted(v) for k, v in prof.get(no, {}).items()}
        allp = [s for s in p.get("all", []) if s[3] >= 3] or p.get("all", [])
        peak = max(allp, key=lambda s: s[1]) if allp else None
        best = min(allp, key=lambda s: s[1]) if allp else None
        lt = latest.get(no)
        rides.append({
            "no": no, "name": b["name"], "ll": b["lightning_lane"], "ll_demand": b["ll_demand"],
            "avg": r1(b["avg_wait"]), "max": b["max_wait"], "uptime": r1(uptime.get(no), 3),
            "down_count": downs.get(no, {}).get("n", 0), "down_min": int(downs.get(no, {}).get("minutes") or 0),
            "peak": {"time": hm(peak[0]), "wait": peak[1]} if peak else None,
            "best": {"time": hm(best[0]), "wait": best[1]} if best else None,
            "latest": {"open": bool(lt["is_open"]), "wait": lt["wait_time"], "time": lt["ts_local"].strftime("%m/%d %H:%M")} if lt else None,
            "profile": {k: [[s[0], s[1], s[2]] for s in v] for k, v in p.items()},
            "hourly": sorted(hourly.get(no, [])),
        })
    rides.sort(key=lambda r: -(r["avg"] or 0))

    # マスタ(rides.json)のどちらにもない名前だけを「未登録」とする。分析対象外として登録済みのものは別に出す
    unmatched = rows(con, """SELECT DISTINCT w.ride_id AS id, w.name FROM fact_waits w
                             WHERE w.park = ? AND w.ride_no IS NULL
                               AND w.ride_id NOT IN (SELECT ride_id FROM dim_ride_other WHERE park = w.park) ORDER BY w.name""", park)
    not_analyzed = rows(con, """SELECT o.ride_id AS id, o.name, o.kind, o.parent_no AS parent, o.note,
                                       (SELECT ANY_VALUE(w.name) FROM fact_waits w WHERE w.park = o.park AND w.ride_id = o.ride_id) AS qt_name
                                FROM dim_ride_other o WHERE o.park = ? ORDER BY o.kind, o.ride_id""", park)
    cov = [d["coverage"] for d in days if d["coverage"] is not None]
    return {
        "park": park, "park_name": PARK_NAME.get(park, park),
        "generated_at": datetime.now(ZoneInfo("Asia/Tokyo")).strftime("%Y-%m-%d %H:%M"),
        "range": {"from": str(rng[2]), "to": str(rng[3]), "days": rng[1], "rows": rng[0],
                  "last_fetch": rng[4].strftime("%Y-%m-%d %H:%M") if rng[4] else None,
                  "coverage": r1(sum(cov) / len(cov), 3) if cov else None},
        "days": [{"date": str(d["date_local"]), "weekday": WEEKDAY.get(d["weekday"], d["weekday"]), "is_weekend": bool(d["is_weekend"]),
                  "holiday": d["holiday"], "event": d["event"], "open": d["open_est"], "close": d["close_est"],
                  "crowd_index": r1(d["crowd_index"]), "runs": d["runs"], "slots": d["slots"], "expected": d["expected"], "coverage": d["coverage"],
                  "median_gap": r1(d["median_gap"]), "max_gap": d["max_gap"]} for d in days],
        "rides": rides,
        "unmatched": unmatched,
        "not_analyzed": not_analyzed,
        "attribution": {"text": "Powered by Queue-Times.com", "url": "https://queue-times.com/"},
    }


# ── 分析計画書(docs/分析計画書.md)に合わせた部分 ─────────────────
# 特殊な日:含める場合と除く場合を比べる(計画書「データの前提と注意点」)
SPECIAL = {"thanksgiving": ("感謝祭の週", "2026-11-26", "2026-11-29"), "christmas": ("クリスマス前", "2026-12-19", "2026-12-26")}


def read_json(path):
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return None


def read_csv(path):
    import csv
    try:
        with open(path, encoding="utf-8-sig", newline="") as f:
            return list(csv.DictReader(f))
    except FileNotFoundError:
        return None


def stamp(path):
    """出力ファイルの更新時刻(日本時間)。古い計算結果を見分けるため"""
    if not os.path.exists(path):
        return None
    return datetime.fromtimestamp(os.path.getmtime(path), ZoneInfo("Asia/Tokyo")).strftime("%Y-%m-%d %H:%M")


def crowd_index_variants(park):
    """Q2 混雑指数。model.py と同じ計算(同じ関数)で、特殊な日を基準に含める/除くの4通り"""
    import model as M
    try:
        rides, W = M.load_w(park)
    except SystemExit:
        return None
    days = sorted({d for r in W.values() for d in r})
    core = [k for k in W if rides[k]["fallback_peak"] >= 40]
    span = lambda a, b: {d for d in days if a <= d <= b}
    tg, xm = span(*SPECIAL["thanksgiving"][1:]), span(*SPECIAL["christmas"][1:])
    out = {}
    for key, excl in {"all": set(), "ex_thanksgiving": tg, "ex_christmas": xm, "ex_both": tg | xm}.items():
        use = [d for d in days if d not in excl]
        if not use:
            continue
        overall = {k: M.mean([w for d, sl in W[k].items() if d in use for w in sl.values()]) for k in W}
        vals = {d: M.day_ci(W, d, overall, core) for d in days}
        out[key] = {d: round(v, 1) for d, v in vals.items() if v is not None}
    return out


def analysis(con, park, base):
    days_n = base["range"]["days"]
    mdl = read_json(f"models/{park}.json")
    bt = read_json(f"models/{park}_backtest_summary.json")
    ins = read_json(f"insights/{park}_summary.json")
    plan = read_json(f"plan_{park}_result.json")
    gbm = read_csv(f"models/{park}_gbm_compare.csv")
    imp = read_csv(f"models/{park}_gbm_importance.csv")
    rides_json = json.load(open("rides.json", encoding="utf-8"))[park]

    # Q3 混雑指数モデル(model.py)。画面で 混雑指数X → 予測 を計算できるよう係数と形を渡す
    q3 = None
    if mdl:
        q3 = {"rides": {k: {"name": rides_json[k]["name"], "a": round(m["a"], 3), "b": round(m["b"], 4), "r2": round(m["r2"], 3), "days": m["days"],
                            "shape": [[int(s), v] for s, v in sorted(m["shape"].items(), key=lambda kv: int(kv[0]))]}
                        for k, m in mdl["rides"].items()},
              "gbm_importance": [{"name": r["条件"], "value": float(r["外すと誤差が何分増えるか"])} for r in (imp or [])][:8]}

    # Q4 精度(model.py --backtest と gbm.py)
    q4 = None
    if bt or gbm:
        q4 = {"backtest": bt and {"days": bt["days"], "all": bt["all"], "top": bt["top"], "per_day": bt["per_day"],
                                  "rides": sorted(({"no": k, "name": rides_json[k]["name"], **v} for k, v in bt["rides"].items()), key=lambda r: -r["known"])},
              "gbm": [{"method": r["予測"], "all": float(r["平均誤差・全体(分)"]),
                       "top": float(r["平均誤差・人気アトラクション(分)"]) if r.get("平均誤差・人気アトラクション(分)") else None,
                       "bands": {b: (float(r[b]) if r.get(b) else None) for b in ["〜10時", "10〜12時", "12〜15時", "15〜18時", "18〜21時", "21時〜"]}}
                      for r in gbm] if gbm else None}

    # Q8 ショー中に空くアトラクション(ノート⑤と同じ:直前30分とショー中の平均待ちの比較)
    has_show = con.execute("SELECT count(*) FROM information_schema.tables WHERE table_name = 'dim_show'").fetchone()[0] > 0
    shows = []
    if has_show:
        for r in rows(con, """
            WITH x AS (
              SELECT s.show_name, f.ride_no, f.name,
                     avg(f.wait_time) FILTER (WHERE f.slot15 >= s.start_min AND f.slot15 < s.end_min) AS during,
                     avg(f.wait_time) FILTER (WHERE f.slot15 >= s.start_min - 30 AND f.slot15 < s.start_min) AS before,
                     min(s.start_min) AS start_min, min(s.end_min) AS end_min, count(DISTINCT f.date_local) AS days
              FROM fact_waits f JOIN dim_show s ON s.park = f.park AND s.date_local = f.date_local
              WHERE f.park = ? AND f.ride_no IS NOT NULL GROUP BY ALL)
            SELECT * FROM x WHERE before >= 15 ORDER BY show_name, during / before""", park):
            shows.append({"show": r["show_name"], "time": f"{hm(r['start_min'])}〜{hm(r['end_min'])}", "no": r["ride_no"], "name": r["name"],
                          "before": r1(r["before"]), "during": r1(r["during"]),
                          "change": r1(100 * (r["during"] / r["before"] - 1)) if r["during"] is not None else None, "days": r["days"]})
    # Q8 ゲスト占有率(ノート⑦と同じ v_queue_people。2時間ごとの平均の割合)
    occ = rows(con, """
        SELECT ride_no, name, (slot15 // 120) * 2 AS block, avg(share) AS share, avg(people_in_line) AS people
        FROM v_queue_people WHERE park = ? AND ride_no IS NOT NULL GROUP BY ALL""", park)
    total = {}
    for r in occ:
        total[r["ride_no"]] = total.get(r["ride_no"], 0) + (r["people"] or 0)
    top = [k for k, _ in sorted(total.items(), key=lambda kv: -kv[1])[:8]]
    occupancy = {"blocks": sorted({r["block"] for r in occ}),
                 "rides": [{"no": k, "name": next(r["name"] for r in occ if r["ride_no"] == k),
                            "share": {str(r["block"]): r1(r["share"], 3) for r in occ if r["ride_no"] == k}} for k in top]}

    # 品質の判定基準(計画書の表と同じ6項目)
    cov = base["range"]["coverage"]
    criteria = [
        {"id": "coverage", "name": "データの充足率", "how": "営業時間の15分枠のうち、記録がある割合", "line": "90%以上",
         "value": None if cov is None else f"{cov:.0%}", "ok": None if cov is None else cov >= 0.9,
         "fallback": "実行ログを確認。大きな欠けの日は分析から外す", "source": "export_dashboard.py"},
        {"id": "error", "name": "待ち時間予測の誤差", "how": "--backtest の平均誤差(混雑指数が分かっている場合、人気アトラクション)", "line": "±10分以内",
         "value": None if not bt else f"±{bt['top']['known']:.1f}分", "ok": None if not bt else bt["top"]["known"] <= 10,
         "fallback": "時間帯の形を平日/週末で分ける、外れ値の日を外す", "source": "model.py --backtest", "min_days": 5},
        {"id": "ci_guess", "name": "混雑指数の見込み精度", "how": "「曜日の平均で仮定」と「指数なし」の誤差の差(人気アトラクション)", "line": "指数なしより小さい",
         "value": None if not bt else f"仮定 ±{bt['top']['unknown']:.1f}分 / 指数なし ±{bt['top']['naive']:.1f}分",
         "ok": None if not bt else bt["top"]["unknown"] < bt["top"]["naive"],
         "fallback": "旅行当日の指数は混雑カレンダーから決める", "source": "model.py --backtest", "min_days": 5},
        {"id": "silhouette", "name": "クラスタの分かれ方", "how": "シルエット係数", "line": "0.25以上",
         "value": None if not ins else f"{ins['silhouette']:.2f}(k={ins['k']})", "ok": None if not ins else ins["silhouette"] >= 0.25,
         "fallback": "特徴量を減らす、グループ数を指定し直す", "source": "insights.py", "min_days": 5},
        {"id": "ari", "name": "クラスタの安定性", "how": "ブートストラップの調整ランド指数(ARI)", "line": "0.75以上",
         "value": None if not ins else f"{ins['ari']:.2f}", "ok": None if not ins else ins["ari"] >= 0.75,
         "fallback": "データが増えるまで参考扱いにする", "source": "insights.py", "min_days": 5},
        {"id": "slack", "name": "プランの余裕", "how": "最終プランの最後の予定と退園時刻の差", "line": "30分以上",
         "value": None if not plan else f"{plan['slack_min']}分", "ok": None if not plan else plan["slack_min"] >= 30,
         "fallback": "省略候補の上から外す", "source": "plan.py"},
    ]

    # 各出力がいつ・何日分で作られたか(古い結果を見分ける)
    outputs = {
        "model": {"file": f"models/{park}.json", "at": stamp(f"models/{park}.json"), "days": len(mdl["daily_ci"]) if mdl else None},
        "backtest": {"file": f"models/{park}_backtest_summary.json", "at": stamp(f"models/{park}_backtest_summary.json"), "days": bt and bt["days"]},
        "gbm": {"file": f"models/{park}_gbm_compare.csv", "at": stamp(f"models/{park}_gbm_compare.csv"), "days": None},
        "insights": {"file": f"insights/{park}_summary.json", "at": stamp(f"insights/{park}_summary.json"), "days": ins and ins["days"]},
        "plan": {"file": f"plan_{park}_result.json", "at": stamp(f"plan_{park}_result.json"), "days": None},
    }

    return {
        "data_days": days_n,
        "special": {k: {"label": v[0], "from": v[1], "to": v[2]} for k, v in SPECIAL.items()},
        "crowd_index": crowd_index_variants(park),
        "q3": q3, "q4": q4,
        "q5": ins and {"k": ins["k"], "silhouette": ins["silhouette"], "ari": ins["ari"], "k_scores": ins["k_scores"], "groups": ins["groups"]},
        "q6": ins and ins["ropedrop"],
        "q7": ins and ins["downtime"],
        "q8": {"shows": shows, "occupancy": occupancy},
        "criteria": criteria,
        "outputs": outputs,
        "plan": plan,
    }


def main():
    if not os.path.exists(DB):
        sys.exit("warehouse/ がありません。先に python warehouse.py を実行してください")
    con = duckdb.connect(DB, read_only=True)
    os.makedirs(OUT, exist_ok=True)
    for park in ("DL", "DCA"):
        data = export(con, park)
        if data is None:
            print(f"[{park}] データなし、スキップ"); continue
        data.update(analysis(con, park, data))
        path = os.path.join(OUT, f"{park}.json")
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, separators=(",", ":"))
        print(f"[{park}] {data['range']['days']}日分・アトラクション{len(data['rides'])} → {path}({os.path.getsize(path) // 1024}KB)")
    con.close()


if __name__ == "__main__":
    main()
