"""分析に使わない記録の決まり(model.py・insights.py・analyze.py・warehouse.py で共通)。標準ライブラリだけで動く。

1. 現地 0:00〜4:59 の記録は使わない
   閉園直後の1回の記録や城のウォークスルーが、翌日の1日分として数えられて混雑指数を壊すため。
2. 閉園後の記録は使わない
   その日に rides.json のアトラクションの半分以上が営業していた最後の時刻を「閉園」とみなし、
   その15分後より後の記録は使わない。閉園後も一部のアトラクションだけ「営業中」のまま残ることがあるため
   (例:DCA 11/25 は23時に閉園したが、3つだけ深夜2時過ぎまで営業中の表示だった)。
   朝は対象にしない(早期入園の時間は一部しか開いていないので、同じ基準だと朝のデータが消えるため)。
data/ の記録はどちらも消さずに残す。年越しなど0時以降も営業する日を分析するなら 1. を見直す。
"""
import csv, glob, json, os
from collections import defaultdict
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

TZ = ZoneInfo("America/Los_Angeles")
DAY_START = 5        # 現地のこの時刻より前は使わない
CLOSE_SHARE = 0.5    # アトラクションのこの割合以上が営業していれば「パークが営業中」
CLOSE_GRACE = 15     # 閉園とみなした時刻から、この分数までは使う


def attraction_ids(park):
    with open("rides.json", encoding="utf-8") as f:
        d = json.load(f)
    return {str(v["queue_times_id"]) for v in d.get(park, {}).values() if v.get("queue_times_id") and not v.get("skip_open_check")}


def close_cutoffs(park):
    """日付(現地, 'YYYY-MM-DD')→ その日の記録を使う最後の時刻(現地, タイムゾーン付き)"""
    ids = attraction_ids(park)
    snap = defaultdict(lambda: [0, 0])   # fetched_utc -> [営業中の数, 全体]
    for path in glob.glob(os.path.join("data", park, "*.csv")):
        with open(path, newline="", encoding="utf-8") as f:
            for r in csv.DictReader(f):
                if r["ride_id"] in ids:
                    s = snap[r["fetched_utc"]]
                    s[0] += r["is_open"] == "1"; s[1] += 1
    last_open = {}
    for t, (n, tot) in snap.items():
        if tot and n >= tot * CLOSE_SHARE:
            ts = datetime.fromisoformat(t.replace("Z", "+00:00")).astimezone(TZ)
            if ts.hour < DAY_START:
                continue
            d = ts.date().isoformat()
            if d not in last_open or ts > last_open[d]:
                last_open[d] = ts
    return {d: ts + timedelta(minutes=CLOSE_GRACE) for d, ts in last_open.items()}


def keeper(park):
    """記録の時刻(現地, タイムゾーン付き)を渡すと、分析に使うなら True を返す関数"""
    cut = close_cutoffs(park)
    def keep(ts):
        if ts.hour < DAY_START:
            return False
        c = cut.get(ts.date().isoformat())
        return c is None or ts <= c
    return keep
