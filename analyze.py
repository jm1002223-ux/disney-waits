"""貯めた待ち時間データを集計して、アトラクションごと・15分ごとの待ち時間の傾向を出す。

使い方:
  python analyze.py --park DL
  python analyze.py --park DCA --from 2026-12-01 --days weekend

出力:
  profiles/<park>.json   … plan.py が使う、15分ごとの待ち時間(中央値)
  profiles/<park>_best.csv … アトラクションごとの空いている時間帯・混む時間帯
Powered by Queue-Times.com (https://queue-times.com/)
"""
import argparse, csv, glob, json, os, statistics
from collections import defaultdict
from datetime import datetime, date
from zoneinfo import ZoneInfo

import cleaning

TZ = ZoneInfo("America/Los_Angeles")
SLOT = 15  # 分
# 分析に使わない記録(現地0〜5時・閉園後)の決まりは cleaning.py


def load(park, d_from, d_to, days):
    keep = cleaning.keeper(park)
    seen, obs = set(), defaultdict(lambda: defaultdict(list))
    n_days = set()
    for path in sorted(glob.glob(os.path.join("data", park, "*.csv"))):
        day = date.fromisoformat(os.path.basename(path)[:10])
        if d_from and day < d_from or d_to and day > d_to:
            continue
        wd = day.weekday() >= 5
        if days == "weekday" and wd or days == "weekend" and not wd:
            continue
        with open(path, newline="", encoding="utf-8") as f:
            for r in csv.DictReader(f):
                if r["is_open"] != "1":
                    continue
                key = (r["ride_id"], r["last_updated"] or r["fetched_utc"])
                if key in seen:
                    continue
                seen.add(key)
                ts = datetime.fromisoformat((r["last_updated"] or r["fetched_utc"]).replace("Z", "+00:00")).astimezone(TZ)
                if not keep(ts):
                    continue
                slot = (ts.hour * 60 + ts.minute) // SLOT * SLOT
                obs[r["ride_id"]][slot].append(int(float(r["wait_time"] or 0)))
                n_days.add(day)
    return obs, n_days


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--park", choices=["DL", "DCA"], required=True)
    ap.add_argument("--from", dest="d_from", type=date.fromisoformat)
    ap.add_argument("--to", dest="d_to", type=date.fromisoformat)
    ap.add_argument("--days", choices=["all", "weekday", "weekend"], default="all")
    a = ap.parse_args()

    rides = json.load(open("rides.json", encoding="utf-8"))[a.park]
    by_qid = {str(v["queue_times_id"]): k for k, v in rides.items()}
    obs, n_days = load(a.park, a.d_from, a.d_to, a.days)
    if not obs:
        raise SystemExit("データがありません。data/{}/ にCSVが溜まっているか確認してください。".format(a.park))

    prof = {}
    for qid, slots in obs.items():
        if qid not in by_qid:
            continue
        num = by_qid[qid]
        prof[num] = {str(s): {"median": statistics.median(v), "n": len(v)} for s, v in sorted(slots.items())}

    os.makedirs("profiles", exist_ok=True)
    meta = {"park": a.park, "days_used": len(n_days), "from": str(min(n_days)), "to": str(max(n_days)), "filter": a.days, "slot_min": SLOT}
    json.dump({"meta": meta, "rides": prof}, open(f"profiles/{a.park}.json", "w", encoding="utf-8"), ensure_ascii=False, indent=1)

    hm = lambda m: f"{m // 60}:{m % 60:02d}"
    with open(f"profiles/{a.park}_best.csv", "w", newline="", encoding="utf-8-sig") as f:
        w = csv.writer(f)
        w.writerow(["番号", "アトラクション", "空いている時間帯", "その時の待ち(分)", "混む時間帯", "その時の待ち(分)", "データ数"])
        rows = []
        for num, sl in prof.items():
            good = [(int(s), x["median"]) for s, x in sl.items() if x["n"] >= 2]
            if not good:
                continue
            lo = min(good, key=lambda z: z[1]); hi = max(good, key=lambda z: z[1])
            rows.append((int(num), rides[num]["name"], hm(lo[0]), lo[1], hm(hi[0]), hi[1], sum(x["n"] for x in sl.values())))
        for r in sorted(rows, key=lambda r: -r[5]):
            w.writerow(r)
    print(f"{a.park}: {len(n_days)}日分({meta['from']}〜{meta['to']})、{len(prof)}アトラクションを集計しました")
    print(f"→ profiles/{a.park}.json, profiles/{a.park}_best.csv")


if __name__ == "__main__":
    main()
