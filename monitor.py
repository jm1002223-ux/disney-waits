"""収集が止まっていないかを点検する(GitHub Actions が1時間おきに実行)。標準ライブラリだけで動く。

  python monitor.py   # 問題がなければ何も出さず終了コード0。問題があれば内容を出して終了コード1

点検すること(パークごとに確実に営業している現地の時間帯だけ。parks.py の check_hours:アメリカ 9〜21時、東京 10〜20時)
  1. 今日のCSVがあり、最後の記録が30分以内か(収集が止まっていないか)
  2. 最後の記録で、rides.json のアトラクションが1つ以上営業中か(閉園判定の誤りや、Queue-Times側の異常)
"""
import csv, json, os, sys
from datetime import datetime, timezone

import parks

PARKS = parks.CODES
STALE_MIN = 30


def attraction_ids(park):
    with open("rides.json", encoding="utf-8") as f:
        d = json.load(f)
    return {str(v["queue_times_id"]) for v in d[park].values() if v.get("queue_times_id") and not v.get("skip_open_check")}


def check(now=None):
    now = now or datetime.now(timezone.utc)
    problems = []
    for park in PARKS:
        tz = parks.tz(park)
        local = now.astimezone(tz)
        start, end = parks.PARKS[park]["check_hours"]
        if not (start <= local.hour < end):
            continue
        path = os.path.join("data", park, f"{local:%Y-%m-%d}.csv")
        if not os.path.exists(path):
            problems.append(f"{park}: 今日({local:%m/%d})の記録がありません")
            continue
        with open(path, newline="", encoding="utf-8") as f:
            rows = list(csv.DictReader(f))
        if not rows:
            problems.append(f"{park}: 今日の記録が空です")
            continue
        last_t = rows[-1]["fetched_utc"]
        age = (now - datetime.strptime(last_t, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)).total_seconds() / 60
        if age > STALE_MIN:
            problems.append(f"{park}: 最後の記録が{age:.0f}分前です(現地 {datetime.fromisoformat(last_t.replace('Z', '+00:00')).astimezone(tz):%H:%M})")
        ids = attraction_ids(park)
        last = [r for r in rows if r["fetched_utc"] == last_t and r["ride_id"] in ids]
        if last and not any(r["is_open"] == "1" for r in last):
            problems.append(f"{park}: 営業時間中なのに、最後の記録でアトラクションがすべて休止です")
    return problems


if __name__ == "__main__":
    ps = check()
    if ps:
        print("\n".join(ps))
        sys.exit(1)
