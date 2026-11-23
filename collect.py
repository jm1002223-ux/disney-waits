"""Queue-Times.com から待ち時間を取得して data/<park>/<現地日付>.csv に追記する。
Powered by Queue-Times.com (https://queue-times.com/)
標準ライブラリだけで動く。"""
import csv, json, os, sys, urllib.request
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

PARKS = {"DL": 16, "DCA": 17}  # Disneyland Park / Disney California Adventure
TZ = ZoneInfo("America/Los_Angeles")
URL = "https://queue-times.com/parks/{}/queue_times.json"
FIELDS = ["fetched_utc", "ride_id", "ride_name", "land", "is_open", "wait_time", "last_updated"]


def fetch(park_id):
    req = urllib.request.Request(URL.format(park_id), headers={"User-Agent": "personal-wait-time-logger"})
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.load(r)


def rows(data, now):
    out = []
    groups = [(l.get("name", ""), l.get("rides", [])) for l in data.get("lands", [])]
    groups.append(("", data.get("rides", [])))
    for land, rides in groups:
        for r in rides:
            out.append({"fetched_utc": now.strftime("%Y-%m-%dT%H:%M:%SZ"), "ride_id": r["id"], "ride_name": r["name"],
                        "land": land, "is_open": int(bool(r.get("is_open"))), "wait_time": r.get("wait_time", 0),
                        "last_updated": r.get("last_updated", "")})
    return out


def main():
    now = datetime.now(timezone.utc)
    local_day = now.astimezone(TZ).strftime("%Y-%m-%d")
    failed = 0
    for code, pid in PARKS.items():
        try:
            rs = rows(fetch(pid), now)
        except Exception as e:  # 1パークの失敗で全体を止めない
            print(f"[{code}] fetch failed: {e}", file=sys.stderr)
            failed += 1
            continue
        if not any(r["is_open"] for r in rs):
            print(f"[{code}] park closed, skip")
            continue
        path = os.path.join("data", code, f"{local_day}.csv")
        os.makedirs(os.path.dirname(path), exist_ok=True)
        # 前回と同じ更新時刻のデータなら書かない(5分更新なので重複を避ける)
        last = None
        if os.path.exists(path):
            with open(path, newline="", encoding="utf-8") as f:
                prev = list(csv.DictReader(f))
            if prev:
                last = {(p["ride_id"], p["last_updated"]) for p in prev[-len(rs):]}
        if last and all((str(r["ride_id"]), r["last_updated"]) in last for r in rs):
            print(f"[{code}] no update since last fetch")
            continue
        new = not os.path.exists(path)
        with open(path, "a", newline="", encoding="utf-8") as f:
            w = csv.DictWriter(f, fieldnames=FIELDS)
            if new:
                w.writeheader()
            w.writerows(rs)
        print(f"[{code}] wrote {len(rs)} rows -> {path}")
    if failed == len(PARKS):
        sys.exit(1)


if __name__ == "__main__":
    main()
