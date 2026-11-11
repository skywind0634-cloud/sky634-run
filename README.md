# sky634 — JRA 血統データベース & 週次予想システム

父系・母系(牝系)・母父・ニックス・距離・馬場・競馬場・ラップ・騎手/調教師を多角的に分析する**血統データベース**と、
それに基づいて毎週金曜に土日のJRAレースから**最大5レース・各10点以内**の推奨馬券を出す予想システム。

- 📅 **今週の予想** → [`predictions/`](predictions/README.md)
- 🧬 **血統分析の設計と知見** → [`docs/血統分析.md`](docs/血統分析.md)
- 📊 **実績DBの自動集計**（種牡馬×条件、実測ニックス、騎手×調教師 …） → [`docs/db_summary.md`](docs/db_summary.md)
- 🔬 **徹底分析レポート**（学習した種牡馬適性・ニックス・牝系・コース別カード・妙味・騎手/厩舎・モデル検証） → [`docs/analysis/`](docs/analysis/README.md)
- 🗂 **血統ナレッジ** → [`data/knowledge/`](data/knowledge)（父系系統樹・種牡馬90頭超のプロファイル・ニックス・名門牝系・JRA10場のコース特性）

## 仕組み

```
JRA公式(JRADB)     ──scraper──▶  data/keiba.db  ──analysis──▶  条件別集計(経験ベイズ縮約)
                                   (結果/5代血統/ラップ/払戻)                 │
data/knowledge/*.json(血統事前知識) ─────────────────────────────────────────┤
cards/(今週の出馬表) ─────────────────────────────────────────────▶ model ─▶ 勝率・3着内率
                                                                             │
                                                         betting(10点以内) ─▶ predictions/<土曜>/README.md
```

## 使い方

```bash
pip install -r requirements.txt
python -m pytest -q

# 過去データの取り込み（結果＋5代血統）と集計
python -m keiba.cli update-results --from 2025-01-01 --to 2026-09-28
python -m keiba.cli analyze
python -m keiba.cli backtest --from 2026-07-01 --to 2026-09-28 --save   # 温度・市場ブレンド比の最適化

# 毎週（金曜）
python -m keiba.cli weekly            # 先週結果取込 → 検証 → 集計 → 今週カード → 予想
```

## 自動化
- **GitHub Actions** `.github/workflows/weekly-data.yml`: 毎週金曜 16:10 JST に JRA公式サイトから結果取り込み〜出馬表(前4走・オッズ付き)〜予想生成を実行しコミット。
  手動実行 (`mode=backfill`, `from`, `to`) で過去データを一括取り込み。
- **Claude の定期実行（毎週金曜・日本時間）**: `CLAUDE.md` の週次手順に従い、Actions の成果を取り込み、
  ネットワーク制限時は Web 検索で出馬表・血統を補完してカードを作り、根拠付き予想を `predictions/` に掲載する。

> 馬券の購入は20歳以上・自己責任で。予測値は的中を保証するものではありません。
