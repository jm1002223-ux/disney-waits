# 引継ぎ:ディズニー待ち時間ロガーと分析(disney-waits)

最終更新:2026-11-23(日本時間)。このファイルは、このリポジトリで作業するClaude Code向けの引継ぎメモ。

## 作業のルール(ユーザー:Ty)
- 返答は**日本語**。専門用語は短く言い換える
- 先にやることを1文で言ってから作業し、終わったら結果を短く報告する。手順の実況はいらない
- 分析期間(〜12/26)は **このリポジトリの技術スタックを変えない**(ユーザーの決定)。新しいライブラリやサービスを足す前に確認する
  - 例外(2026-11-23 ユーザー承認):ダッシュボード用に `dashboard/`(Next.js一式)と Vercel を追加。収集・分析のPythonは変えない
- `data/` の中身は手で編集しない(GitHub Actionsが追記するため、編集すると `git pull` が衝突する)
- トークンやキーをファイルやコミットに書かない。`gh` は入っているが**未ログイン**(`C:\Program Files\GitHub CLI\gh.exe`)。push は git(資格情報は保存済み)で行う。ブラウザでのGitHub操作(設定・手動実行)はユーザーが自分でやる方が速いと言っている

## 目的
カリフォルニアのディズニーランド・リゾート2パーク(ディズニーランド・パーク=DL、カリフォルニア・アドベンチャー=DCA)の待ち時間を5分おきに集め、12/26(土)までに、旅行当日に使う「最適な回り方」を、実データと精度の裏付け付きで作る。個人の研究。公開はしない(将来、英語で発表する可能性はある)。

- 分析計画書:`docs/分析計画書.md`(原本 https://claude.ai/artifact/YKAfkorAq67qjSs6pbUQcP)
- セットアップ手順書:`docs/セットアップ手順書.md`(原本 https://claude.ai/artifact/E6fZJJYofrUKZ8o6QhvR7a)
- 旅行の日付と、各パークに行く日:**未確定**(決まったら `plan_*.json` の `date` と `crowd_index` に入れる)

## 現在の状況(2026-11-23時点)
- **セットアップ完了**:公開リポジトリ https://github.com/jm1002223-ux/disney-waits (`main`)にpush済み。Actionsの書き込み権限を設定し、手動実行(2026-11-23 13:24 UTC)は成功
- **本物のデータ取得を確認済み**:`data/DCA/2026-11-23.csv`(31行)。列は想定どおりの7列で、カンマを含む名前(`Monsters, Inc. …`)も正しく入る。この1回は閉園中に保存された(下記の判定変更の前)。行はすべて休止扱いで、分析への影響はない。`data/` なので消さない
- **collect.py の営業判定を変更**(2026-11-23):夜間もWorld of Colorなどのショーが `is_open` になり、DCAの閉園を判定できなかった。判定は `rides.json` に載っているアトラクションだけで行う。閉園直後の1回だけ記録する(`park just closed, write once`)。ローカルで5つの場面と本物のデータで確認済み
- Queue-Timesの一覧にあって分析しない17件(DL 11、DCA 6)は、`rides.json` の `_not_analyzed` に登録済み(2026-11-24)。シングルライダーの列は12/7の基礎分析でスタンバイとの差を見る
- **GitHubの定期実行(schedule)はこのアカウントで起動しない**(2026-11-23 15:00〜22:20 UTC、cronの書き方・ファイル名の変更でも0回。このアカウントで定期実行が動いたことは一度もない)。**2026-11-23 22:24 UTC から「自分で次の回を予約する方式」に変更して稼働中**(下の `collect-waits.yml` の行)。PCでの代行(`local_collect.sh`)は停止済み
  - 毎日の確認:Actions に `in_progress` 1つと `pending` 1つがあること、`data/` に `wait-time-bot` のコミットが5分おきに入っていること。鎖が切れたら(両方ない)Actionsの画面で手動実行すれば再開する。Windowsで collect.py を動かすときは `PYTHONIOENCODING=utf-8` が必要
- PCの分析環境:仮想環境 `C:\Users\user\venvs\disney-waits`(`requirements.txt` と `tzdata` を導入済み)。Windowsストア版Pythonのままだと、JupyterLabのインストールがパスの長さの上限で失敗するため。使う前に `C:\Users\user\venvs\disney-waits\Scripts\Activate.ps1`

## 技術スタック
| 役割 | 使うもの |
| --- | --- |
| データ元 | Queue-Times.com 公開API `https://queue-times.com/parks/{id}/queue_times.json`(DL=16, DCA=17)。キー不要、約5分ごとに更新、現在値のみ |
| 定期実行 | GitHub Actions(`.github/workflows/collect-waits.yml`、公開リポジトリなので無料) |
| 言語 | Python 3.12(3.10以上で動く) |
| 生データ | CSV:`data/<DL|DCA>/<現地の日付>.csv` |
| 分析用DB | DuckDB と Parquet(`warehouse/`、パーク・月で分割。git管理外) |
| 処理・学習・図 | pandas、scikit-learn(HistGradientBoostingRegressor、k-means、GroupKFold)、matplotlib、joblib |
| 分析環境 | JupyterLab(`analysis.ipynb`) |
| ルート最適化 | 自作(焼きなまし法、`plan.py`) |
| ダッシュボード | `dashboard/`:Next.js 16.2.6 + React 19.2.4 + Tailwind 4.2.2 + Recharts 3.8.1 + lucide-react(`music-lesson-portal` のUIを流用、版も同じに固定)。Node.js 24 |
| 公開先 | Vercel(CLIで手動デプロイ)。環境変数 `DASHBOARD_PASSWORD` によるパスワード(Basic認証、`dashboard/proxy.ts`)付き |

`requirements.txt`:duckdb, pandas, matplotlib, jupyterlab, scikit-learn。Windowsでは `tzdata` も入れる。

## ファイルの役割
| ファイル | 役割 |
| --- | --- |
| `.github/workflows/collect-waits.yml` | 1回の実行で約5時間50分、5分おきに `collect.py` を実行して `data/` をコミット。開始直後に `gh workflow run` で次の回を予約(`concurrency` で前の回が終わるまで待機)。起動は手動実行か、このファイルの変更のpush。`permissions: contents: write, actions: write`。止めるときは「Disable workflow」。1時間おきに集計(`summary/`)と点検(`monitor.py`、異常ならIssue〈ラベル monitor〉を立て回復で閉じる)。終了時にも次の回を予約(保険)。`permissions` に `issues: write` |
| `collect.py` | 両パークを取得し、`data/<park>/<現地日付>.csv` に追記。列:`fetched_utc, ride_id, ride_name, land, is_open, wait_time, last_updated`。営業判定は `rides.json` のアトラクションだけで行う(ショー・シングルライダーの列は数えない)。全部閉まっていればスキップ(ログ `park closed, skip`)。閉園直後は1回だけ記録。更新がなければスキップ(`no update since last fetch`)。ログの1行目は `アトラクション営業中 n/全体` |
| (追加の出力) | ダッシュボード用の要約JSON:`model.py --backtest` → `models/<park>_backtest_summary.json`、`insights.py` → `insights/<park>_summary.json`(シルエット・ARI・時間帯別のシス調を含む)、`plan.py` → `plan_<park>_result.json`(**`plan_<park>.json` は入力の設定なので別名**)。計算方法は変えていない |
| `analyze.py` | 15分ごとの中央値・90%点 → `profiles/`。`--park`、`--from/--to`、`--days all/weekday/weekend` |
| `model.py` | 混雑指数(人気アトラクションの日平均÷期間平均×100)、予測モデル(日平均 = a + b×混雑指数、×時間帯の形)、ゲスト占有率(リトルの法則)、レポートHTML → `models/`。`--backtest` で1日ずつ抜いて精度検証 |
| `insights.py` | クラスタリング(k-means++、シルエットでk決定、ブートストラップARI)、朝いちばんの価値ランキング、シス調(営業中の停止)の確率と時間帯 → `insights/`。`--boot`、`--seed` |
| `warehouse.py` | CSV → DuckDB+Parquet。テーブル `fact_waits`、`dim_ride`、`dim_calendar`(米国祝日、ホリデー期間、営業時間、混雑指数、`calendar_extra.csv`)、`dim_ride_other`(分析対象外の登録済み項目)、`dim_show`(列名は `show_name`。`show` は予約語なので使わない)。ビュー `v_slot_profile`、`v_daily_ride`、`v_downtime_events`、`v_queue_people` |
| `gbm.py` | 勾配ブースティングと他の方式を比較(A〜Eの5方式、日単位のGroupKFold、並べ替え重要度)。`models/<park>_gbm.joblib` を保存。`--fast` |
| `plan.py` | 1日の回り方を最適化。待ち時間の出し方は `wait_model` で `median` / `crowd_index` / `gbm` を選ぶ。出力 `plan_<park>.md`。**マルチパスは優先順位どおりに予約する**(ユーザーの決定。合計時間の最小化で選ぶと、パスの列は約10分なので必ずパスになるため)。候補から外すもの:スタンバイ平均が `ll_min_standby` 未満、戻り時刻+バッファ(`ll_buffer_min`)が `ll_use_until` に入らない、`ll_skip`。焼きなまし法で決めるのは、パスを使うタイミングとそれ以外の順番だけ。`--fast` / `--robust` / `--no-compare` |
| `plan_DL.json` / `plan_DCA.json` | 入退園時刻、混雑指数、乗りたいもの(`multi_pass`/`standby` はどちらでも同じ扱い)、シングルパス、優先度、ショー、食事、パスの設定(`ll_use_until`:DL 23:00/DCA 21:00〈閉園22時の1時間前、ユーザー指定〉、`ll_buffer_min` 15、`ll_min_standby` 30、`ll_priority`、`ll_skip`、`ll_delay_high/mid`)、反復回数 |
| `rides.json` | アトラクションの対応表(番号、座標、1時間の処理人数の推定、パス種別)。DL 47、DCA 25。TDL/TDSも入っているが未使用。`"skip_open_check": true` は営業判定から外す(城のウォークスルー)。**`"_not_analyzed"`** は Queue-Times に出るが分析しない項目(鉄道の駅・ショー・体験・シングルライダーの列。`kind`・`parent`)。ここに載っていない名前だけがダッシュボードで「未登録」になる。トップのキーを全部回すコードは `_` で始まるキーを飛ばすこと |
| `calendar_extra.csv` | 日ごとのイベント・営業時間・天気(手で追記) |
| `shows.csv` | ショーの時刻(`*` は毎日。公式アプリに合わせて手で直す) |
| `parks.py` | パークごとのID・タイムゾーン。**まだどこからも使っていない**(東京対応の途中) |
| `export_dashboard.py` | ダッシュボード用の集計を `dashboard/data/<park>.json` に書き出す。**分析計画書の構成どおり**:品質(15分枠の充足率・実行間隔・名前の対応)、Q1(15分プロファイル)、Q2(model.py と同じ関数で、感謝祭の週/クリスマス前を基準に含める・除くの4通り)、Q3〜Q7(models/・insights/ の出力を読む)、Q8(ノート⑤⑦と同じSQL)、品質の判定基準6項目、最終プラン(`plan_<park>_result.json`)、各出力の計算日時と日数 |
| `monitor.py` | 収集の点検(現地9〜21時のみ):今日のCSVの最後の記録が30分以内か、最後の記録でアトラクションが1つ以上営業中か。問題があれば終了コード1。Actionsが1時間おきに実行 |
| `summary/` | Actionsが書き出すダッシュボード用の集計(`DL.json`・`DCA.json`)。手で編集しない |
| `dashboard/` | ダッシュボード(Next.js)。タブは計画書の成果物の5つ(①品質 11/30、②基礎分析 12/7、③予測と分類 12/14、④繁忙期 12/21、⑤最終プラン 12/26)。各Qに計画書の問い・手法・必要日数・初回日を表示し、日数不足は「参考値」、出力がなければ実行するコマンドを表示。`app/page.tsx` がサーバー側で `data/*.json` を読む(`public/` には置かない)。`DASHBOARD_DATA_DIR` を指定するとその集計を読み「サンプル表示中」の帯を出す。`data/*.json` は git 管理外、`.vercelignore` では除外しない。手元は `npm run dev`(パスワードなし) |
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
python export_dashboard.py   # ダッシュボード用の集計を書き出す
cd dashboard && npx vercel --prod   # 公開中のダッシュボードを更新(Vercel CLI。GitHub連携はしない:連携するとJSONなしでビルドされる)
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
- ダッシュボードは**親しい友人に見せる程度の私的な範囲**(ユーザーの決定、2026-11-23)。パスワード必須、検索エンジンには載せない(noindex)、出すのは集計値だけ、フッターに Queue-Times の表記。それ以上に広く見せるなら、事前にQueue-Timesへ相談

## 知っておくべき前提・落とし穴
- 時刻:GitHubはUTC、データの日付は現地(America/Los_Angeles)、ユーザーは日本時間。12月は日本が17時間進んでいる。collect・analyze・model・insights・warehouse はタイムゾーンを `America/Los_Angeles` に固定している
- cronはPST(UTC-8)前提。夏時間になる3月以降も使うなら時間帯を見直す
- GitHubの混雑で、実行が10〜15分おきになることがある(分析は15分単位なので問題なし)
- **ホーンテッドマンションの「13分」は「ほぼ待ちなし」の意味**(13は不吉な数字の演出。ユーザー指摘、データで確認:空いている時間帯だけに出て、5分・10分は一度も出ない)。そのまま平均すると空いた時間帯が長めになるので、分析では扱い(何分とみなすか)を決めてから使う。`data/` は直さない
- 表示待ち時間は実際より長めのことが多い。順番の比較には使えるが、分数は余裕を持って読む
- ライトニングレーンの戻り時刻は取れないので、プランは見込み値を使う。処理人数も推定値
- シス調は5分未満の停止を数え落とす
- **混雑指数の定義が2つある(既存の不一致)**:`model.py` は「rides.json の fallback_peak ≥ 40 のアトラクション」、`warehouse.py` の `dim_calendar.crowd_index`(ノート①・gbm.py が使う)は「実データの期間平均 ≥ 40」。ダッシュボードのQ2は予測・プランと揃えるため model.py 側。**決定(2026-11-24、ユーザー承認)**:12/7までは model.py 側のまま。12/7〜12/14に実データで3案(①model.py の推定ピーク≥40、②warehouse の実平均≥40、③最初の1週間の実データで選んで固定)を `--backtest` で比べ、計画書の判定基準(人気アトラクションの誤差、「曜日の平均で仮定」<「指数なし」)が良い方に統一する。比較用の切り替えはその時に model.py へ足す
- アトラクションの休止や名前の変更があると、`rides.json` にない名前が記録に出る。月曜の作業で確認する
- パスのルール:マルチパスは対象ごとに1日1回、次の予約は使った後か予約から2時間後。ライズ・オブ・ザ・レジスタンスとラジエーター・スプリングス・レーサーはシングルパスのみ(1日1回、両方買える)。早期入園は2026/1/5で終了

## 止めていること・残りの仕事
- **東京対応(保留中)**:`parks.py` を各スクリプトに組み込む(タイムゾーン、日本の祝日、`--park` の選択肢にTDL/TDS、cronを `*/5 * * * *`、`plan_TDL.json`/`plan_TDS.json`、README)。ユーザーが再開を言うまで手を付けない
- **ダッシュボード公開済み(2026-11-24)**:https://disney-waits-dashboard.vercel.app (Vercelプロジェクト `disney-waits-dashboard`、パスワードは `DASHBOARD_PASSWORD`〈Secret、ユーザーだけが知る〉)。パスワードなし・誤りは401、noindex を確認済み。**データは自動更新されない**(`export_dashboard.py` → `cd dashboard && npx vercel --prod --yes`)。`vercel link` がGitHub連携を勝手に付けたので `vercel git disconnect` で外した。リンクし直したら必ず外すこと(5分おきのデータコミットのたびにJSONなしで本番が上書きされる)
- 12/26で分析が終わったら、Actionsの `collect-wait-times` を「Disable workflow」で止める
- 任意の候補(未依頼):Queue-Timesへ過去データの問い合わせメール(英語)
