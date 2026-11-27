"""パークの設定(Queue-TimesのID・タイムゾーン・国)と祝日。パークを足すときは PARKS に1行足す。
標準ライブラリだけで動く(collect.py・monitor.py も使うため)。"""
from datetime import date, timedelta
from zoneinfo import ZoneInfo

# check_hours:monitor.py が点検する現地の時間帯(確実に営業している時間)
PARKS = {
    "DL":  {"id": 16,  "tz": "America/Los_Angeles", "country": "US", "name": "ディズニーランド・パーク", "check_hours": (9, 21)},
    "DCA": {"id": 17,  "tz": "America/Los_Angeles", "country": "US", "name": "ディズニー・カリフォルニア・アドベンチャー", "check_hours": (9, 21)},
    "TDL": {"id": 274, "tz": "Asia/Tokyo",          "country": "JP", "name": "東京ディズニーランド", "check_hours": (10, 20)},
    "TDS": {"id": 275, "tz": "Asia/Tokyo",          "country": "JP", "name": "東京ディズニーシー", "check_hours": (10, 20)},
}
CODES = tuple(PARKS)


def tz(park):
    return ZoneInfo(PARKS[park]["tz"])


def _nth(y, m, wd, n):
    d = date(y, m, 1); d += timedelta((wd - d.weekday()) % 7); return d + timedelta(7 * (n - 1))


def _last(y, m, wd):
    d = date(y, m + 1, 1) - timedelta(1) if m < 12 else date(y, 12, 31); return d - timedelta((d.weekday() - wd) % 7)


def us_holidays(years):
    """アメリカの祝日(連邦祝日+パークが混む日)"""
    out = {}
    for y in years:
        out.update({date(y, 1, 1): "元日", _nth(y, 1, 0, 3): "キング牧師記念日", _nth(y, 2, 0, 3): "大統領の日", _last(y, 5, 0): "メモリアルデー",
                    date(y, 6, 19): "ジューンティーンス", date(y, 7, 4): "独立記念日", _nth(y, 9, 0, 1): "レイバーデー", _nth(y, 10, 0, 2): "コロンブスデー",
                    date(y, 11, 11): "退役軍人の日", _nth(y, 11, 3, 4): "感謝祭", _nth(y, 11, 3, 4) + timedelta(1): "感謝祭の翌日",
                    date(y, 12, 24): "クリスマス・イブ", date(y, 12, 25): "クリスマス", date(y, 12, 31): "大晦日"})
    return out


def jp_holidays(years):
    """日本の祝日(振替休日・国民の休日を含む)+パークが混む日(クリスマス・年末年始)。2000〜2099年用"""
    out = {}
    for y in years:
        k = y - 1980
        h = {date(y, 1, 1): "元日", _nth(y, 1, 0, 2): "成人の日", date(y, 2, 11): "建国記念の日", date(y, 2, 23): "天皇誕生日",
             date(y, 3, int(20.8431 + 0.242194 * k - k // 4)): "春分の日", date(y, 4, 29): "昭和の日",
             date(y, 5, 3): "憲法記念日", date(y, 5, 4): "みどりの日", date(y, 5, 5): "こどもの日",
             _nth(y, 7, 0, 3): "海の日", date(y, 8, 11): "山の日", _nth(y, 9, 0, 3): "敬老の日",
             date(y, 9, int(23.2488 + 0.242194 * k - k // 4)): "秋分の日", _nth(y, 10, 0, 2): "スポーツの日",
             date(y, 11, 3): "文化の日", date(y, 11, 23): "勤労感謝の日"}
        # 国民の休日:祝日にはさまれた平日
        for d in sorted(h):
            m = d + timedelta(1)
            if m not in h and m + timedelta(1) in h and m.weekday() != 6:
                h[m] = "国民の休日"
        # 振替休日:祝日が日曜なら、その後の最初の祝日でない日
        for d in sorted(h):
            if d.weekday() == 6:
                s = d + timedelta(1)
                while s in h:
                    s += timedelta(1)
                h[s] = "振替休日"
        out.update(h)
        for d, n in {date(y, 12, 24): "クリスマス・イブ", date(y, 12, 25): "クリスマス", date(y, 12, 31): "大晦日",
                     date(y, 1, 2): "正月", date(y, 1, 3): "正月"}.items():
            out.setdefault(d, n)
    return out


def holidays(park, years):
    return (jp_holidays if PARKS[park]["country"] == "JP" else us_holidays)(years)
