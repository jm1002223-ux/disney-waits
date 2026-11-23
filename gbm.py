"""勾配ブースティングで待ち時間を予測する(warehouse.py の後に実行)。

  python gbm.py --park DL            # 精度の比較 + 学習済みモデルの保存
  python gbm.py --park DL --fast     # 比較を軽くする(分割数3)

勾配ブースティングとは:
  「条件で分けていく小さな決定木」をたくさん作り、前の木が外したぶんを次の木が直す、をくり返して
  予測を積み上げる手法。曜日×時間帯×混み具合×天気のような、条件の組み合わせで決まる数字の予測が得意。
  ここでは scikit-learn の HistGradientBoostingRegressor(LightGBMと同じ方式)を使う。

比べる5つの予測(日ごとに分けて、学習に使っていない日で採点する = 交差検証)
  A. 過去の平均            … アトラクション×15分枠の過去の平均(何も工夫しない基準)
  B. 混雑指数モデル        … model.py と同じ考え方(日平均 = a + b×混雑指数、×時間帯の形)
  C. GBM(事前・指数あり)  … 曜日・祝日・時間帯・営業時間・天気・ショー + その日の混雑指数
  D. GBM(事前・指数なし)  … C から混雑指数を抜いたもの(何も調べずに前日までに予測する場合)
  E. GBM(当日・30分先)    … D + 30分前・60分前のそのアトラクションの待ち時間(当日に組み直す用)

出力
  models/<park>_gbm_compare.csv     … 5つの予測の平均誤差(全体・人気アトラクション・時間帯別)
  models/<park>_gbm_importance.csv  … どの条件が予測に効いているか(並べ替え重要度)
  models/<park>_gbm.joblib          … 学習済みモデル(plan.py が "wait_model": "gbm" で使う)
Powered by Queue-Times.com (https://queue-times.com/)
"""
import argparse, json, os, sys

import duckdb
import joblib
import numpy as np
import pandas as pd
from sklearn.ensemble import HistGradientBoostingRegressor
from sklearn.inspection import permutation_importance
from sklearn.model_selection import GroupKFold

DB = "warehouse/disney.duckdb"
CAT = ["ride", "weather", "event"]
BASE = ["ride", "slot", "since_open", "hours_est", "dow", "is_weekend", "is_holiday", "holiday_season", "weather", "event", "show_on", "month_day"]
FEATS = {"C": BASE + ["crowd_index"], "D": BASE, "E": BASE + ["lag30", "lag60"]}


def load(park):
    if not os.path.exists(DB):
        sys.exit("先に python warehouse.py を実行してください")
    con = duckdb.connect(DB, read_only=True)
    has_show = con.execute("SELECT count(*) FROM information_schema.tables WHERE table_name = 'dim_show'").fetchone()[0] > 0
    show_sql = """EXISTS (SELECT 1 FROM dim_show s WHERE s.park = w.park AND s.date_local = w.date_local
                          AND w.slot15 >= s.start_min - 30 AND w.slot15 < s.end_min)""" if has_show else "false"
    df = con.execute(f"""
        WITH w AS (
            SELECT park, ride_no, date_local, slot15, median(wait_time) AS wait
            FROM fact_waits WHERE park = ? AND wait_time IS NOT NULL AND ride_no IS NOT NULL GROUP BY ALL)
        SELECT w.ride_no, w.date_local, w.slot15, w.wait,
               c.dow, c.is_weekend::INT AS is_weekend, (c.holiday IS NOT NULL)::INT AS is_holiday, c.holiday_season::INT AS holiday_season,
               c.hours_est, c.crowd_index, coalesce(c.weather, '') AS weather, coalesce(c.event, '') AS event,
               w.slot15 - (CAST(split_part(c.open_est, ':', 1) AS INT) * 60 + CAST(split_part(c.open_est, ':', 2) AS INT)) AS since_open,
               ({show_sql})::INT AS show_on
        FROM w JOIN dim_calendar c USING (park, date_local)
        ORDER BY w.ride_no, w.date_local, w.slot15""", [park]).df()
    con.close()
    if df.empty:
        sys.exit(f"{park} のデータがありません")
    df["ride"] = df.ride_no.astype(str)
    df["slot"] = df.slot15
    df["month_day"] = pd.to_datetime(df.date_local).dt.dayofyear
    # 当日用:30分前・60分前の待ち時間(同じアトラクション・同じ日)
    df = df.sort_values(["ride", "date_local", "slot"])
    for lag in (30, 60):
        prev = df[["ride", "date_local", "slot", "wait"]].copy()
        prev["slot"] = prev.slot + lag
        df = df.merge(prev.rename(columns={"wait": f"lag{lag}"}), on=["ride", "date_local", "slot"], how="left")
    for c in CAT:
        df[c] = df[c].astype("category")
    return df


def model():
    return HistGradientBoostingRegressor(max_iter=400, learning_rate=0.06, max_leaf_nodes=31, min_samples_leaf=20,
                                         l2_regularization=1.0, categorical_features="from_dtype", random_state=0)


def pred_A(tr, te):
    m = tr.groupby(["ride", "slot"], observed=True).wait.mean()
    r = tr.groupby("ride", observed=True).wait.mean()
    return np.array([m.get((a, b), r.get(a, tr.wait.mean())) for a, b in zip(te.ride, te.slot)])


def pred_B(tr, te):
    out = np.zeros(len(te))
    for ride, g in te.groupby("ride", observed=True):
        t = tr[tr.ride == ride]
        if t.empty:
            out[te.ride == ride] = tr.wait.mean(); continue
        day = t.groupby("date_local").agg(dm=("wait", "mean"), ci=("crowd_index", "first")).dropna()
        b, a = np.polyfit(day.ci, day.dm, 1) if len(day) >= 3 and day.ci.std() > 0 else (0.0, day.dm.mean())
        t = t.merge(day.dm.rename("dm"), left_on="date_local", right_index=True)
        shape = (t.wait / t.dm.replace(0, np.nan)).groupby(t.slot).mean()
        base = np.clip(a + b * g.crowd_index.to_numpy(), 0, None)
        out[(te.ride == ride).to_numpy()] = base * g.slot.map(shape).fillna(1.0).to_numpy()
    return out


def main():
    ap = argparse.ArgumentParser(); ap.add_argument("--park", choices=["DL", "DCA"], required=True)
    ap.add_argument("--fast", action="store_true"); a = ap.parse_args()
    df = load(a.park)
    days = df.date_local.nunique()
    if days < 4:
        sys.exit(f"比較には4日分以上必要です(今は{days}日分)")
    k = min(3 if a.fast else 7, days)
    rides = json.load(open("rides.json", encoding="utf-8"))[a.park]
    popular = {r for r, v in rides.items() if v["fallback_peak"] >= 60}
    preds = {x: np.full(len(df), np.nan) for x in "ABCDE"}
    for i, (tri, tei) in enumerate(GroupKFold(n_splits=k).split(df, groups=df.date_local)):
        tr, te = df.iloc[tri], df.iloc[tei]
        preds["A"][tei] = pred_A(tr, te)
        preds["B"][tei] = pred_B(tr, te)
        for x in "CDE":
            m = model().fit(tr[FEATS[x]], tr.wait)
            preds[x][tei] = np.clip(m.predict(te[FEATS[x]]), 0, None)
        print(f"  分割 {i + 1}/{k} 完了", flush=True)

    names = {"A": "A 過去の平均", "B": "B 混雑指数モデル", "C": "C GBM(事前・指数あり)", "D": "D GBM(事前・指数なし)", "E": "E GBM(当日・30分先)"}
    err = {x: np.abs(preds[x] - df.wait.to_numpy()) for x in "ABCDE"}
    pop = df.ride.isin(popular).to_numpy()
    band = pd.cut(df.slot, [0, 600, 720, 900, 1080, 1260, 1440], labels=["〜10時", "10〜12時", "12〜15時", "15〜18時", "18〜21時", "21時〜"], right=False)
    os.makedirs("models", exist_ok=True)
    rows = []
    for x in "ABCDE":
        r = {"予測": names[x], "平均誤差・全体(分)": round(float(np.nanmean(err[x])), 1), "平均誤差・人気アトラクション(分)": round(float(np.nanmean(err[x][pop])), 1) if pop.any() else None}
        for b in band.cat.categories:
            msk = (band == b).to_numpy()
            r[f"{b}"] = round(float(np.nanmean(err[x][msk])), 1) if msk.any() else None
        rows.append(r)
    comp = pd.DataFrame(rows); comp.to_csv(f"models/{a.park}_gbm_compare.csv", index=False, encoding="utf-8-sig")

    # 全データで学習して保存(plan.py用は事前予測のC・D)
    full = {x: model().fit(df[FEATS[x]], df.wait) for x in "CDE"}
    cats = {c: list(df[c].cat.categories) for c in CAT}
    joblib.dump({"models": full, "features": FEATS, "categories": cats, "park": a.park,
                 "days": [str(d) for d in sorted(df.date_local.unique())]}, f"models/{a.park}_gbm.joblib")
    # 並べ替え重要度(Cモデル、直近の日のサンプルで)
    samp = df.sample(min(len(df), 20000), random_state=0)
    imp = permutation_importance(full["C"], samp[FEATS["C"]], samp.wait, n_repeats=3, random_state=0, scoring="neg_mean_absolute_error")
    label = {"ride": "アトラクション", "slot": "時刻", "since_open": "開園からの経過", "hours_est": "営業時間の長さ", "dow": "曜日", "is_weekend": "週末",
             "is_holiday": "祝日", "holiday_season": "ホリデー期間", "weather": "天気", "event": "イベント", "show_on": "ショーの時間帯", "month_day": "時期(年内の日)", "crowd_index": "混雑指数"}
    impdf = pd.DataFrame({"条件": [label[f] for f in FEATS["C"]], "外すと誤差が何分増えるか": imp.importances_mean.round(2)}).sort_values("外すと誤差が何分増えるか", ascending=False)
    impdf.to_csv(f"models/{a.park}_gbm_importance.csv", index=False, encoding="utf-8-sig")

    print(f"\n{a.park}: {days}日分、{len(df):,}件で比較しました({k}分割の交差検証)")
    print(comp[["予測", "平均誤差・全体(分)", "平均誤差・人気アトラクション(分)"]].to_string(index=False))
    print("\n予測に効いている条件(上位5):")
    print(impdf.head(5).to_string(index=False))
    print(f"\n→ models/{a.park}_gbm_compare.csv, models/{a.park}_gbm_importance.csv, models/{a.park}_gbm.joblib")


if __name__ == "__main__":
    main()
