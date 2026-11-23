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
            WHERE hour(r.ts_local) * 60 + minute(r.ts_local) BETWEEN w.o AND w.o + w.hours_est * 60)
        SELECT w.date_local, w.weekday, w.is_weekend, w.holiday, w.event, w.open_est, w.close_est, w.hours_est, w.crowd_index,
               count(r.ts_local) AS runs, median(r.gap) AS median_gap, max(r.gap) AS max_gap
        FROM win w LEFT JOIN r USING (date_local) GROUP BY ALL ORDER BY w.date_local""", park, park)
    for d in days:
        exp = (d["hours_est"] or 0) * 60 / 5
        d["expected"] = int(exp)
        d["coverage"] = r1(min(1.0, d["runs"] / exp) if exp else None, 3)

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

    unmatched = rows(con, """SELECT DISTINCT ride_id AS id, name FROM fact_waits
                             WHERE park = ? AND ride_no IS NULL ORDER BY name""", park)
    cov = [d["coverage"] for d in days if d["coverage"] is not None]
    return {
        "park": park, "park_name": PARK_NAME.get(park, park),
        "generated_at": datetime.now(ZoneInfo("Asia/Tokyo")).strftime("%Y-%m-%d %H:%M"),
        "range": {"from": str(rng[2]), "to": str(rng[3]), "days": rng[1], "rows": rng[0],
                  "last_fetch": rng[4].strftime("%Y-%m-%d %H:%M") if rng[4] else None,
                  "coverage": r1(sum(cov) / len(cov), 3) if cov else None},
        "days": [{"date": str(d["date_local"]), "weekday": WEEKDAY.get(d["weekday"], d["weekday"]), "is_weekend": bool(d["is_weekend"]),
                  "holiday": d["holiday"], "event": d["event"], "open": d["open_est"], "close": d["close_est"],
                  "crowd_index": r1(d["crowd_index"]), "runs": d["runs"], "expected": d["expected"], "coverage": d["coverage"],
                  "median_gap": r1(d["median_gap"]), "max_gap": d["max_gap"]} for d in days],
        "rides": rides,
        "unmatched": unmatched,
        "attribution": {"text": "Powered by Queue-Times.com", "url": "https://queue-times.com/"},
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
        path = os.path.join(OUT, f"{park}.json")
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, separators=(",", ":"))
        print(f"[{park}] {data['range']['days']}日分・アトラクション{len(data['rides'])} → {path}({os.path.getsize(path) // 1024}KB)")
    con.close()


if __name__ == "__main__":
    main()
