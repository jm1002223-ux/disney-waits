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


def attraction_ids():
    """営業中かどうかの判定に使うアトラクション(rides.json に載っているもの)。
    ショー(World of Color など)やシングルライダーの列は夜間も「営業中」になることがあるので数えない。"""
    try:
        with open("rides.json", encoding="utf-8") as f:
            d = json.load(f)
        return {code: {str(v["queue_times_id"]) for v in d.get(code, {}).values() if v.get("queue_times_id")} for code in PARKS}
    except Exception as e:  # 読めないときは全件で判定(従来どおり)
        print(f"rides.json を読めないため全件で判定: {e}", file=sys.stderr)
        return {}


def last_snapshot(path):
    """今日のCSVで最後に保存した回の行(なければ空)。"""
    if not os.path.exists(path):
        return []
    with open(path, newline="", encoding="utf-8") as f:
        prev = list(csv.DictReader(f))
    if not prev:
        return []
    t = prev[-1]["fetched_utc"]
    return [p for p in prev if p["fetched_utc"] == t]


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
    attr = attraction_ids()
    for code, pid in PARKS.items():
        try:
            rs = rows(fetch(pid), now)
        except Exception as e:  # 1パークの失敗で全体を止めない
            print(f"[{code}] fetch failed: {e}", file=sys.stderr)
            failed += 1
            continue
        ids = attr.get(code) or {str(r["ride_id"]) for r in rs}
        judged = [r for r in rs if str(r["ride_id"]) in ids]
        n_open = sum(r["is_open"] for r in judged)
        ignored = [r["ride_name"] for r in rs if r["is_open"] and str(r["ride_id"]) not in ids]
        note = f"(判定外で営業中: {', '.join(ignored)})" if ignored else ""
        print(f"[{code}] アトラクション営業中 {n_open}/{len(judged)} {note}")
        path = os.path.join("data", code, f"{local_day}.csv")
        prev = last_snapshot(path)
        if n_open == 0:
            # 閉園直後の1回だけは記録する(最後に営業していた時刻をデータに残すため)
            was_open = any(p["is_open"] == "1" and p["ride_id"] in ids for p in prev)
            if not was_open:
                print(f"[{code}] park closed, skip")
                continue
            print(f"[{code}] park just closed, write once")
        os.makedirs(os.path.dirname(path), exist_ok=True)
        # 前回と同じ更新時刻のデータなら書かない(5分更新なので重複を避ける)
        last = {(p["ride_id"], p["last_updated"]) for p in prev}
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
