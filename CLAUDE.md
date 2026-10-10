# sky634 — JRA 血統データベース & 週次予想システム

## 目的
JRA の全レースを対象に、父系・母系(牝系)・母父・ニックス・距離・馬場・競馬場・ラップ・騎手/調教師を多角的に分析する血統DBを構築・毎週更新し、
毎週金曜（日本時間）に土日のレースの推奨馬券を、血統DBの根拠付きで `predictions/` に掲載する。

## 構成
- `data/knowledge/*.json` — 血統ナレッジ（事前知識）。父系系統樹・種牡馬プロファイル・ニックス・牝系・コース特性
- `data/keiba.db` — 実績DB (SQLite)。races / results / horses(5代血統) / entries
- `keiba/` — Python パッケージ（scraper / analysis / model / betting / report / cli）
- `cards/YYYY-MM-DD/*.json` — 出馬表カード（予想入力）。形式は `cards/README.md`
- `predictions/YYYY-MM-DD/README.md` — 週次予想（土曜の日付フォルダ）。`picks.json` と `review.md`（検証）
- `docs/` — 血統分析の解説 (`血統分析.md`) と自動集計 (`db_summary.md`)

## 週次手順（金曜・日本時間に実行）
1. `git fetch origin main && git merge origin/main` で、GitHub Actions (`weekly-data.yml`、main ブランチで実行) が作った最新の `data/keiba.db`・`cards/`・`predictions/` を取り込む（`data/keiba.db` が衝突したら main 側を採用）。
2. `pip install -r requirements.txt && python -m pytest -q`
3. ネットワークで JRA公式サイト(www.jra.go.jp)に届く場合: `python -m keiba.cli weekly` だけで結果取込→集計→カード→予想まで完了（データ源は JRA 公式。`--source netkeiba` で切替可）。
4. 届かない場合（コンテナのネットワーク制限で jra.go.jp が遮断されている場合）: まず main に GitHub Actions が作ったカード `cards/<日付>/` があればそれを使う。無ければ:
   - WebSearch で今週末（土・日）の重賞・特別レースの出馬表（馬番・枠・騎手・斤量）、各馬の父・母・母父、近走成績（日付・クラス・騎手・斤量・着順・距離・走破タイムと勝ち馬とのタイム差・通過順・上がり3F順位・そのレースのラップ型）、前売りオッズを調べる。距離・ペース・脚質の分析に通過順と距離は必須。
   - 候補は各日の重賞＋メイン格の特別戦を中心に 6〜10 レース。`cards/<日付>/<race_id>.json` を `cards/README.md` の形式で作成する（分かる項目だけでよい）。
   - race_id は netkeiba 形式 `YYYY + 場コード(05東京,06中山,08京都,09阪神 …) + 回 + 日 + R`。不明なら `YYYYMMDD-場-R` でも可。
   - 先週末の主要レース結果も WebSearch で確認し、ナレッジと食い違う点（新しい活躍種牡馬、ニックス、馬場傾向）があれば `data/knowledge/*.json` を更新する。
4.5 専門家見解の更新（亀谷敬正・望田潤・水上学・坂上明大など）:
   - `git fetch origin sources` で木曜に GitHub Actions (`fetch-sources.yml`) が取得したコラム本文（`sources/` ブランチ）を読む。無ければ WebSearch で今週の重賞・メイン格の「血統」コラム・予想コメントを探す。
   - 血統に関する具体的な主張（種牡馬/系統 × 条件 × プラス/マイナス）を `data/knowledge/expert_notes.json` に要点と出典URLのみで追加する（本文は転載しない。条件のキーは同ファイルの schema を参照）。
   - `python -m keiba.cli deep-analysis` で実績による裏付け確認（`docs/analysis/expert_check.md`）。裏付けのあるものだけが予想に小さく反映される。
5. `python -m keiba.cli predict --weekend <土曜の日付>` → `predictions/<土曜>/README.md` を確認し、
   必要なら「血統的根拠」の下に WebSearch で得た補足（調教・陣営コメント・馬場見込み）を追記する。モデルの確率・買い目は改変しない。
6. 先週分 `python -m keiba.cli review --weekend <先週土曜>`（結果がDBにある場合）。
7. コミットして、作業ブランチに push。

## ルール
- 対象は全競馬場の**第7レース以降**のみ。**未勝利戦と障害は除外**（取り込み・予想とも。`keiba/config.py` の `is_target_race`）。
- 本線の買い方（2026-10 のバックテストで決定, `docs/analysis/strategy.md`）: 妙味馬（4〜9番人気・予測勝率が市場の1.3倍以上・人気帯の中で走る条件がプラス）の単勝・複勝＋妙味馬を含む馬連（期待値の比1.2以上・想定2000円以上、14頭以下のレースで最大5点）。`keiba/betting.py` の `value_plan`。
- 推奨レース数は固定しない（本線が成立するレース全部）。重賞は推奨外でも印と★を【参考】で載せる。買い目は1レース10点以内。
- 準本線: 4〜9番人気で人気帯の中で走る条件が0.4以上の馬（本線以外・最大2頭）の単勝を少額（検証で単勝回収率100%前後、本線と合わせて105%前後）。レースごとに「買い目カード」（本線・準本線・遊び）を必ず示す（`keiba/digest.py` の `ticket_card`）。
- 予想を伝えるときは、本線だけでなく注目馬一覧（★・専門家の見解・走る条件・妙味条件・牝系・危険な人気馬, `keiba/digest.py`）も根拠付きでチャットに全部出す（ユーザーは予想ページを見に行かない）。
- JRA発売の海外レース: 海外市場のオッズから勝率を出し、期待値＝海外の勝率×JRA単勝で評価（日本馬に人気が偏り外国馬が割安になりやすい）。軸は海外の勝率が最上位（期待値1以上）の馬、期待値1.3以上は単複、軸から期待値1.2以上へ馬連。`python -m keiba.overseas data/overseas/<name>.json`（2026年凱旋門賞の反省: 期待値最上位を軸にして外した）。
- 予想の根拠は必ず血統DB（ナレッジ＋実績集計）に紐付けて記載する。
- スクレイピングは `REQUEST_INTERVAL` 以上の間隔を守り、取得済みページはキャッシュする。
- 馬券は自己責任である旨の注意書きを残す。
