"""集めたCSVを分析用のデータベース(DuckDB + Parquet)にまとめる。

  pip install -r requirements.txt
  python warehouse.py

できるもの:
  warehouse/parquet/waits/park=DL/month=2026-12/*.parquet … 待ち時間の記録(列指向・圧縮)
  warehouse/disney.duckdb … 下のテーブル・ビューをまとめたデータベース

テーブル(SQLで自由に結合できる)
  fact_waits         待ち時間の記録 1行 = 1回の取得 × 1アトラクション(重複は除去済み)
  dim_ride           アトラクションの属性(rides.json):番号・名前・座標・処理人数・パス対象
  dim_calendar       日付の属性:曜日・週末・祝日・ホリデー期間・営業時間(推定)・混雑指数・calendar_extra.csv の内容
  dim_show           ショーの時刻(shows.csv。日付が * の行は毎日)
ビュー(よく使う集計)
  v_slot_profile     アトラクション × 15分ごとの待ち時間(中央値・平均・件数)
  v_daily_ride       アトラクション × 日の平均待ち・最大待ち・運営率
  v_downtime_events  営業中に止まった区間(開始・終了・分)
  v_queue_people     列の人数の推定(リトルの法則)と占有率
いつでも全部作り直すので、何度実行してもよい(データが増えたら実行し直す)。
Powered by Queue-Times.com (https://queue-times.com/)
"""
import glob, json, os, sys
from datetime import date, timedelta

import duckdb

DB = "warehouse/disney.duckdb"
PQ = "warehouse/parquet/waits"


def us_holidays(years):
    """アメリカの祝日(連邦祝日+パークが混む日)"""
    out = {}
    def nth(y, m, wd, n):
        d = date(y, m, 1); d += timedelta((wd - d.weekday()) % 7); return d + timedelta(7 * (n - 1))
    def last(y, m, wd):
        d = date(y, m + 1, 1) - timedelta(1) if m < 12 else date(y, 12, 31); return d - timedelta((d.weekday() - wd) % 7)
    for y in years:
        out.update({date(y, 1, 1): "元日", nth(y, 1, 0, 3): "キング牧師記念日", nth(y, 2, 0, 3): "大統領の日", last(y, 5, 0): "メモリアルデー",
                    date(y, 6, 19): "ジューンティーンス", date(y, 7, 4): "独立記念日", nth(y, 9, 0, 1): "レイバーデー", nth(y, 10, 0, 2): "コロンブスデー",
                    date(y, 11, 11): "退役軍人の日", nth(y, 11, 3, 4): "感謝祭", nth(y, 11, 3, 4) + timedelta(1): "感謝祭の翌日",
                    date(y, 12, 24): "クリスマス・イブ", date(y, 12, 25): "クリスマス", date(y, 12, 31): "大晦日"})
    return out


def main():
    files = glob.glob("data/*/*.csv")
    if not files:
        sys.exit("data/ にCSVがありません")
    os.makedirs("warehouse", exist_ok=True)
    con = duckdb.connect(DB)
    con.execute("SET TimeZone='UTC'")

    # 1) CSV → Parquet(パーク・月ごとに分割)
    con.execute(f"""
    CREATE OR REPLACE TEMP TABLE raw AS
    SELECT regexp_extract(filename, 'data[/\\\\]([A-Z]+)[/\\\\]', 1) AS park,
           CAST(ride_id AS INTEGER) AS ride_id, ride_name, land,
           CAST(is_open AS INTEGER) AS is_open, CAST(wait_time AS INTEGER) AS wait_time,
           CAST(fetched_utc AS TIMESTAMPTZ) AS fetched_utc,
           TRY_CAST(NULLIF(last_updated, '') AS TIMESTAMPTZ) AS last_updated
    FROM read_csv('data/*/*.csv', filename=true, header=true, all_varchar=true)
    """)
    con.execute(f"""
    CREATE OR REPLACE TEMP TABLE clean AS
    SELECT *, timezone('America/Los_Angeles', fetched_utc) AS ts_local
    FROM raw
    QUALIFY row_number() OVER (PARTITION BY park, ride_id, coalesce(last_updated, fetched_utc) ORDER BY fetched_utc) = 1
    """)
    if os.path.exists(PQ):
        import shutil; shutil.rmtree(PQ)
    os.makedirs(os.path.dirname(PQ), exist_ok=True)
    con.execute(f"""COPY (SELECT *, strftime(ts_local, '%Y-%m') AS month FROM clean)
                   TO '{PQ}' (FORMAT PARQUET, PARTITION_BY (park, month), COMPRESSION ZSTD)""")

    # 2) dim_ride
    rides = json.load(open("rides.json", encoding="utf-8"))
    rows = [(p, int(n), v["queue_times_id"], v["name"], v["x"], v["y"], v["ride_min"], v.get("capacity_per_hour"), v.get("lightning_lane"), v.get("ll_demand"))
            for p, rs in rides.items() for n, v in rs.items()]
    con.execute("CREATE OR REPLACE TABLE dim_ride(park VARCHAR, ride_no INTEGER, ride_id INTEGER, name VARCHAR, x DOUBLE, y DOUBLE, ride_min INTEGER, capacity_per_hour INTEGER, lightning_lane VARCHAR, ll_demand VARCHAR)")
    con.executemany("INSERT INTO dim_ride VALUES (?,?,?,?,?,?,?,?,?,?)", rows)

    # 3) fact_waits(Parquetを直接参照するビュー。番号と15分枠を付ける)
    con.execute(f"""
    CREATE OR REPLACE VIEW fact_waits AS
    SELECT w.park, w.ride_id, r.ride_no, coalesce(r.name, w.ride_name) AS name, w.land,
           w.fetched_utc, w.last_updated, w.ts_local, CAST(w.ts_local AS DATE) AS date_local,
           (hour(w.ts_local) * 60 + minute(w.ts_local)) // 15 * 15 AS slot15,
           hour(w.ts_local) AS hour_local, w.is_open, CASE WHEN w.is_open = 1 THEN w.wait_time END AS wait_time
    FROM read_parquet('{PQ}/**/*.parquet', hive_partitioning = true) w
    LEFT JOIN dim_ride r ON r.park = w.park AND r.ride_id = w.ride_id
    """)

    # 4) dim_calendar(営業時間の推定・混雑指数・祝日・追加情報)
    days = [r[0] for r in con.execute("SELECT DISTINCT date_local FROM fact_waits").fetchall()]
    hol = us_holidays(sorted({d.year for d in days} | {d.year + 1 for d in days}))
    con.execute("CREATE OR REPLACE TEMP TABLE hol(date_local DATE, holiday VARCHAR)")
    con.executemany("INSERT INTO hol VALUES (?,?)", list(hol.items()))
    extra = "SELECT * FROM read_csv('calendar_extra.csv', header=true, all_varchar=true)" if os.path.exists("calendar_extra.csv") else \
            "SELECT NULL::VARCHAR date, NULL::VARCHAR park, NULL::VARCHAR event, NULL::VARCHAR hours_open, NULL::VARCHAR hours_close, NULL::VARCHAR weather, NULL::VARCHAR note WHERE false"
    con.execute(f"""
    CREATE OR REPLACE TABLE dim_calendar AS
    WITH open_slots AS (
        SELECT park, date_local, slot15, avg(is_open) AS share_open FROM fact_waits GROUP BY ALL),
    hours AS (
        SELECT park, date_local, min(slot15) AS open_min, max(slot15) + 15 AS close_min
        FROM open_slots WHERE share_open >= 0.5 GROUP BY ALL),
    ride_avg AS (   -- 混雑指数:人気アトラクション(全期間平均40分以上)の日平均 ÷ 全期間平均
        SELECT park, ride_id, avg(wait_time) AS m FROM fact_waits WHERE wait_time IS NOT NULL GROUP BY ALL HAVING avg(wait_time) >= 40),
    ci AS (
        SELECT f.park, f.date_local, 100 * avg(d.dm / r.m) AS crowd_index
        FROM (SELECT park, date_local, ride_id, avg(wait_time) AS dm FROM fact_waits WHERE wait_time IS NOT NULL GROUP BY ALL) d
        JOIN ride_avg r USING (park, ride_id)
        JOIN (SELECT DISTINCT park, date_local FROM fact_waits) f USING (park, date_local)
        GROUP BY ALL),
    ex AS ({extra})
    SELECT h.park, h.date_local, dayname(h.date_local) AS weekday, isodow(h.date_local) AS dow,
           isodow(h.date_local) >= 6 AS is_weekend, hol.holiday,
           (month(h.date_local) = 12 OR (month(h.date_local) = 11 AND day(h.date_local) >= 14) OR (month(h.date_local) = 1 AND day(h.date_local) <= 7)) AS holiday_season,
           printf('%d:%02d', h.open_min // 60, h.open_min % 60) AS open_est, printf('%d:%02d', h.close_min // 60 % 24, h.close_min % 60) AS close_est,
           (h.close_min - h.open_min) / 60.0 AS hours_est, round(ci.crowd_index, 1) AS crowd_index,
           ex.event, ex.hours_open, ex.hours_close, ex.weather, ex.note
    FROM hours h
    LEFT JOIN ci USING (park, date_local)
    LEFT JOIN hol USING (date_local)
    LEFT JOIN ex ON CAST(ex.date AS DATE) = h.date_local AND (ex.park IS NULL OR ex.park = h.park)
    """)

    # 5) dim_show
    if os.path.exists("shows.csv"):
        con.execute("""CREATE OR REPLACE TABLE dim_show AS
            SELECT c.park, c.date_local, s.show AS show_name,
                   CAST(split_part(s.start, ':', 1) AS INT) * 60 + CAST(split_part(s.start, ':', 2) AS INT) AS start_min,
                   CAST(split_part(s."end", ':', 1) AS INT) * 60 + CAST(split_part(s."end", ':', 2) AS INT) AS end_min
            FROM read_csv('shows.csv', header=true, all_varchar=true) s
            JOIN dim_calendar c ON c.park = s.park AND (s.date = '*' OR CAST(s.date AS DATE) = c.date_local)""")

    # 6) よく使うビュー
    con.execute("""
    CREATE OR REPLACE VIEW v_slot_profile AS
    SELECT park, ride_no, name, slot15, printf('%d:%02d', slot15 // 60, slot15 % 60) AS time,
           median(wait_time) AS median_wait, avg(wait_time) AS avg_wait, quantile_cont(wait_time, 0.9) AS p90_wait, count(*) AS n
    FROM fact_waits WHERE wait_time IS NOT NULL GROUP BY ALL""")
    con.execute("""
    CREATE OR REPLACE VIEW v_daily_ride AS
    SELECT f.park, f.date_local, f.ride_no, f.name, avg(f.wait_time) AS avg_wait, max(f.wait_time) AS max_wait,
           avg(f.is_open) FILTER (WHERE (hour(f.ts_local) * 60 + minute(f.ts_local)) BETWEEN
               (CAST(split_part(c.open_est, ':', 1) AS INT) * 60 + CAST(split_part(c.open_est, ':', 2) AS INT))
               AND (CAST(split_part(c.open_est, ':', 1) AS INT) * 60 + c.hours_est * 60)) AS uptime
    FROM fact_waits f JOIN dim_calendar c USING (park, date_local) GROUP BY ALL""")
    con.execute("""
    CREATE OR REPLACE VIEW v_downtime_events AS
    WITH s AS (
        SELECT park, ride_no, name, date_local, ts_local, is_open,
               lag(is_open) OVER w AS prev_open,
               sum(CASE WHEN is_open = 1 THEN 1 ELSE 0 END) OVER (PARTITION BY park, ride_id, date_local ORDER BY ts_local ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW) AS opened_so_far,
               sum(CASE WHEN is_open = 1 THEN 1 ELSE 0 END) OVER (PARTITION BY park, ride_id, date_local ORDER BY ts_local ROWS BETWEEN CURRENT ROW AND UNBOUNDED FOLLOWING) AS opens_later,
               ride_id
        FROM fact_waits WINDOW w AS (PARTITION BY park, ride_id, date_local ORDER BY ts_local)),
    marks AS (   -- 営業開始後〜最後の運営までの間に、運営中→停止 になった所から次に動くまで
        SELECT *, sum(CASE WHEN is_open = 0 AND prev_open = 1 THEN 1 ELSE 0 END) OVER (PARTITION BY park, ride_id, date_local ORDER BY ts_local) AS grp
        FROM s WHERE opened_so_far > 0 AND opens_later > 0)
    SELECT park, ride_no, name, date_local, min(ts_local) AS down_from,
           (SELECT min(ts_local) FROM s s2 WHERE s2.park = m.park AND s2.ride_id = m.ride_id AND s2.date_local = m.date_local AND s2.ts_local > max(m.ts_local) AND s2.is_open = 1) AS up_again,
           hour(min(ts_local)) AS start_hour
    FROM marks m WHERE is_open = 0 AND grp > 0 GROUP BY park, ride_id, ride_no, name, date_local, grp""")
    con.execute("""
    CREATE OR REPLACE VIEW v_queue_people AS
    WITH q AS (
        SELECT p.park, p.ride_no, p.name, p.slot15, p.time, p.median_wait, r.capacity_per_hour,
               r.capacity_per_hour / 60.0 * p.median_wait AS people_in_line
        FROM v_slot_profile p JOIN dim_ride r USING (park, ride_no))
    SELECT *, people_in_line / sum(people_in_line) OVER (PARTITION BY park, slot15) AS share
    FROM q""")

    n = con.execute("SELECT count(*), count(DISTINCT date_local), min(date_local), max(date_local) FROM fact_waits").fetchone()
    print(f"DuckDB: {DB}  /  Parquet: {PQ}")
    print(f"  記録 {n[0]:,} 行、{n[1]} 日分({n[2]}〜{n[3]})")
    for t in ["fact_waits", "dim_ride", "dim_calendar", "dim_show", "v_slot_profile", "v_daily_ride", "v_downtime_events", "v_queue_people"]:
        try:
            print(f"  {t:18s} {con.execute(f'SELECT count(*) FROM {t}').fetchone()[0]:>10,} 行")
        except duckdb.Error as e:
            print(f"  {t:18s} (なし: {str(e).splitlines()[0][:60]})")
    con.close()


if __name__ == "__main__":
    main()
