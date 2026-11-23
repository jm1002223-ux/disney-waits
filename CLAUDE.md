# 引継ぎ:ディズニー待ち時間ロガーと分析(disney-waits)

最終更新:2026-11-23(日本時間)。このファイルは、このリポジトリで作業するClaude Code向けの引継ぎメモ。

## 作業のルール(ユーザー:Ty)
- 返答は**日本語**。専門用語は短く言い換える
- 先にやることを1文で言ってから作業し、終わったら結果を短く報告する。手順の実況はいらない
- 分析期間(〜12/26)は **このリポジトリの技術スタックを変えない**(ユーザーの決定)。新しいライブラリやサービスを足す前に確認する
- `data/` の中身は手で編集しない(GitHub Actionsが追記するため、編集すると `git pull` が衝突する)
- トークンやキーをファイルやコミットに書かない。GitHubの操作は `gh`(`gh auth login` 済み)で行う

## 目的
カリフォルニアのディズニーランド・リゾート2パーク(ディズニーランド・パーク=DL、カリフォルニア・アドベンチャー=DCA)の待ち時間を5分おきに集め、12/26(土)までに、旅行当日に使う「最適な回り方」を、実データと精度の裏付け付きで作る。個人の研究。公開はしない(将来、英語で発表する可能性はある)。

- 分析計画書:`docs/分析計画書.md`(原本 https://claude.ai/artifact/YKAfkorAq67qjSs6pbUQcP)
- セットアップ手順書:`docs/セットアップ手順書.md`(原本 https://claude.ai/artifact/E6fZJJYofrUKZ8o6QhvR7a)
- 旅行の日付と、各パークに行く日:**未確定**(決まったら `plan_*.json` の `date` と `crowd_index` に入れる)

## 現在の状況(2026-11-23時点)
- コードは一式できていて、ダミーデータでは全スクリプトの動作を確認済み
- **未実施**:GitHubの公開リポジトリ `disney-waits` の作成、push、Actionsの書き込み権限の設定、手動実行での確認
- **未確認**:Queue-Times の本物のデータ取得(開発環境から接続できなかった)。最初の本番実行のログで、CSVの列と中身を必ず確かめる
- データ取得の開始予定:2026-11-24(現地)。日本時間では 11/25 0時ごろから

## 技術スタック
| 役割 | 使うもの |
| --- | --- |
| データ元 | Queue-Times.com 公開API `https://queue-times.com/parks/{id}/queue_times.json`(DL=16, DCA=17)。キー不要、約5分ごとに更新、現在値のみ |
| 定期実行 | GitHub Actions(`.github/workflows/collect.yml`、公開リポジトリなので無料) |
| 言語 | Python 3.12(3.10以上で動く) |
| 生データ | CSV:`data/<DL|DCA>/<現地の日付>.csv` |
| 分析用DB | DuckDB と Parquet(`warehouse/`、パーク・月で分割。git管理外) |
| 処理・学習・図 | pandas、scikit-learn(HistGradientBoostingRegressor、k-means、GroupKFold)、matplotlib、joblib |
| 分析環境 | JupyterLab(`analysis.ipynb`) |
| ルート最適化 | 自作(焼きなまし法、`plan.py`) |

`requirements.txt`:duckdb, pandas, matplotlib, jupyterlab, scikit-learn。Windowsでは `tzdata` も入れる。

## ファイルの役割
| ファイル | 役割 |
| --- | --- |
| `.github/workflows/collect.yml` | cron `*/5 0-8,15-23 * * *`(UTC)= 現地7時〜24時ごろ。`collect.py` を実行して `data/` をコミット。`workflow_dispatch` で手動実行可。`permissions: contents: write` |
| `collect.py` | 両パークを取得し、`data/<park>/<現地日付>.csv` に追記。列:`fetched_utc, ride_id, ride_name, land, is_open, wait_time, last_updated`。全部閉まっている、または更新がないときはスキップ(ログ `park closed, skip`) |
| `analyze.py` | 15分ごとの中央値・90%点 → `profiles/`。`--park`、`--from/--to`、`--days all/weekday/weekend` |
| `model.py` | 混雑指数(人気アトラクションの日平均÷期間平均×100)、予測モデル(日平均 = a + b×混雑指数、×時間帯の形)、ゲスト占有率(リトルの法則)、レポートHTML → `models/`。`--backtest` で1日ずつ抜いて精度検証 |
| `insights.py` | クラスタリング(k-means++、シルエットでk決定、ブートストラップARI)、朝いちばんの価値ランキング、シス調(営業中の停止)の確率と時間帯 → `insights/`。`--boot`、`--seed` |
| `warehouse.py` | CSV → DuckDB+Parquet。テーブル `fact_waits`、`dim_ride`、`dim_calendar`(米国祝日、ホリデー期間、営業時間、混雑指数、`calendar_extra.csv`)、`dim_show`(列名は `show_name`。`show` は予約語なので使わない)。ビュー `v_slot_profile`、`v_daily_ride`、`v_downtime_events`、`v_queue_people` |
| `gbm.py` | 勾配ブースティングと他の方式を比較(A〜Eの5方式、日単位のGroupKFold、並べ替え重要度)。`models/<park>_gbm.joblib` を保存。`--fast` |
| `plan.py` | 1日の回り方を最適化。待ち時間の出し方は `wait_model` で `median` / `crowd_index` / `gbm` を選ぶ。出力 `plan_<park>.md` |
| `plan_DL.json` / `plan_DCA.json` | 入退園時刻、混雑指数、マルチパス・シングルパス・スタンバイの対象、優先度、ショー、食事、パスの戻り時刻の見込み(`ll_delay_high/mid`)、反復回数 |
| `rides.json` | アトラクションの対応表(番号、座標、1時間の処理人数の推定、パス種別)。DL 47、DCA 25。TDL/TDSも入っているが未使用 |
| `calendar_extra.csv` | 日ごとのイベント・営業時間・天気(手で追記) |
| `shows.csv` | ショーの時刻(`*` は毎日。公式アプリに合わせて手で直す) |
| `parks.py` | パークごとのID・タイムゾーン。**まだどこからも使っていない**(東京対応の途中) |
| `analysis.ipynb` | 9つの分析とSQLの自由欄。日本語フォントは自動で選ぶ |
| `README.md` | 日本語の全体説明 |

## いつもの作業(毎週月曜、分析計画書どおり)
```bash
git pull
python warehouse.py
python model.py --park DL && python model.py --park DL --backtest
python model.py --park DCA && python model.py --park DCA --backtest
python insights.py --park DL && python insights.py --park DCA
python gbm.py --park DL      # 10日分たまってから
jupyter lab analysis.ipynb
```
必要な日数の目安:`analyze`・`plan` 1日〜、`model` 3日〜、`--backtest`・`insights` 5〜7日〜、GBMとクラスタリングは10〜14日〜。

## 分析計画(11/24〜12/26)
| 期限 | 成果物 |
| --- | --- |
| 11/30(月) | データ品質レポート(欠け、実行間隔、アトラクション名の対応) |
| 12/7(月) | 基礎分析(時間帯の傾向、平日と週末、シス調の初回集計、朝いちばんの価値) |
| 12/14(月) | 予測モデルと分類(混雑指数モデル vs 勾配ブースティング、精度検証、クラスタリング) |
| 12/21(月) | 繁忙期の反映(クリスマス前を含めたモデル更新、ゲスト占有率、ショー中に空く場所) |
| 12/26(土) | 最終プラン(両パークの回り方PDF、省略候補、分析レポート一式) |

問いはQ1〜Q8(詳しくは分析計画書):Q1 時間帯ごとの混み方、Q2 混雑指数、Q3 指数と時刻から待ち時間を予測、Q4 その精度、Q5 似たアトラクションのグループ、Q6 朝いちばんに乗る順番、Q7 シス調、Q8 ショー中の空きとゲストの偏り。

**合格ライン**:データの充足率90%以上/人気アトラクションの予測誤差 平均±10分以内/混雑指数の見込みが「指数なし」より良い/シルエット0.25以上/ブートストラップARI 0.75以上/最終プランの余裕30分以上。下回ったら、プランは中央値(混雑指数なし)で計算する。

**特殊な日**:感謝祭の週(11/26〜11/29)とクリスマス前(12/19〜12/26)は、含める場合と除く場合を比べる。12/24・12/25は `calendar_extra.csv` に公式の営業時間を入れる。

## 守ること(データの扱い)
- 図やレポートには「Powered by Queue-Times.com」とリンク(https://queue-times.com/)を必ず入れる
- 集めた生データを再配布しない(リポジトリは公開だが、配布物にはしない)。外に出すなら事前にQueue-Timesへ相談
- Queue-Timesのウェブページ(過去データのページなど)はスクレイピングしない。使うのは公開APIだけ
- ディズニー公式の画像・ロゴは使わない

## 知っておくべき前提・落とし穴
- 時刻:GitHubはUTC、データの日付は現地(America/Los_Angeles)、ユーザーは日本時間。12月は日本が17時間進んでいる。collect・analyze・model・insights・warehouse はタイムゾーンを `America/Los_Angeles` に固定している
- cronはPST(UTC-8)前提。夏時間になる3月以降も使うなら時間帯を見直す
- GitHubの混雑で、実行が10〜15分おきになることがある(分析は15分単位なので問題なし)
- 表示待ち時間は実際より長めのことが多い。順番の比較には使えるが、分数は余裕を持って読む
- ライトニングレーンの戻り時刻は取れないので、プランは見込み値を使う。処理人数も推定値
- シス調は5分未満の停止を数え落とす
- アトラクションの休止や名前の変更があると、`rides.json` にない名前が記録に出る。月曜の作業で確認する
- パスのルール:マルチパスは対象ごとに1日1回、次の予約は使った後か予約から2時間後。ライズ・オブ・ザ・レジスタンスとラジエーター・スプリングス・レーサーはシングルパスのみ(1日1回、両方買える)。早期入園は2026/1/5で終了

## 止めていること・残りの仕事
- **東京対応(保留中)**:`parks.py` を各スクリプトに組み込む(タイムゾーン、日本の祝日、`--park` の選択肢にTDL/TDS、cronを `*/5 * * * *`、`plan_TDL.json`/`plan_TDS.json`、README)。ユーザーが再開を言うまで手を付けない
- 12/26で分析が終わったら、Actionsの `collect-wait-times` を「Disable workflow」で止める
- 任意の候補(未依頼):Queue-Timesへ過去データの問い合わせメール(英語)
