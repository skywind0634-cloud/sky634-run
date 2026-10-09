# 分析レポート（取り込みデータから自動生成）

- 対象: 9622 レース / 131007 走（2020-12-13 〜 2026-10-04、第7R以降・未勝利/障害除く）
- 全体: 勝率 7.4% / 複勝率 22.1%
- 学習した種牡馬 202 頭・母父 261 頭 → `data/knowledge/learned_sires.json`

| レポート | 内容 |
|---|---|
| [sires.md](sires.md) | 種牡馬の学習適性（12軸）、条件別の強い種牡馬、道悪・ペース別、母父・母父系統 |
| [nicks_families.md](nicks_families.md) | 実測ニックス（全体比・父内相対）、系統×系統、兄弟の成績が優秀な母、名門牝系 |
| [courses.md](courses.md) | コース別カード（荒れ度・1番人気・ラップ型・脚質・枠・血統・騎手・厩舎） |
| [market_value.md](market_value.md) | 人気別成績、回収率で見た妙味と過剰人気の条件 |
| [human_conditions.md](human_conditions.md) | 騎手・調教師・コンビ、ローテ、距離変化、季節、馬場×脚質、頭数 |
| [course_form.md](course_form.md) | 直線の長さ・坂・大回り/小回り・回り・頭数 × 脚質／種牡馬 |
| [crosses.md](crosses.md) | 5代以内のクロス（祖先・濃さ別）の人気比と期間別の再現性（5代血統表の補完に応じて自動更新） |
| [country_types.md](country_types.md) | 国別タイプ（日本型・米国型・欧州型）の年別・条件別の人気比と、開催の偏りが続くかの検証 |
| [family.md](family.md) | 牝系（兄弟・2代母の一族）の条件適性の検証と、有力馬を出し続けている牝系 |
| [trends.md](trends.md) | 傾向の波: 同名レースの連続好走血統・血統の勢い・今の開催の馬場傾向（翌年/翌週も続くかの検証つき） |
| [value_segments.md](value_segments.md) | 条件×人気帯の回収率（発見→確認→未使用期間テストの3段階で検証した妙味条件） |
| [expert_check.md](expert_check.md) | 専門家見解（亀谷・望田・水上・坂上 等）の実績による検証 |
| [learned_weights.md](learned_weights.md) | 市場（人気）を土台に学習した各要素の重みと、期待値で選んだ場合の回収率 |
| [backtest.md](backtest.md) | 予想モデルの検証（的中率・回収率・キャリブレーション・要素の貢献度） |
