# 出馬表カード（予想の入力データ）

`cards/YYYY-MM-DD/<race_id>.json` に1レース1ファイルで置く。
`python -m keiba.cli build-cards` が netkeiba から自動生成するが、ネットワーク制限で取得できない場合は
Web検索で調べた情報から手動（または Claude）で作成してよい。**分かる項目だけ埋めればよい**（未記入は無視される）。

```json
{
  "race_id": "202605040211",
  "date": "2026-10-04",
  "course": "東京",
  "race_no": 11,
  "name": "毎日王冠",
  "grade": "G2",
  "surface": "芝",
  "distance": 1800,
  "going": "良",
  "expected_pace": "瞬発",
  "entries": [
    {
      "number": 1, "gate": 1, "name": "馬名", "sex": "牡", "age": 4, "weight": 57,
      "jockey": "騎手名", "trainer": "調教師名",
      "sire": "父", "dam": "母", "damsire": "母父",
      "odds": 3.4,
      "body_weight_diff": 4,
      "style": "先行",
      "recent": [
        {"date": "2026-08-17", "course": "札幌", "surface": "芝", "distance": 2000,
         "grade": "G2", "finish": 2, "n_runners": 14, "going": "良", "last3f": 34.8,
         "passing": "3-3-2-2", "last3f_rank": 2, "pace_type": "持続",
         "jockey": "騎手名", "weight_carried": 57, "time_sec": 119.8, "behind": 0.1}
      ],
      "pedigree": {"S": "父", "SS": "父の父", "D": "母", "DS": "母父", "DD": "母の母"}
    }
  ]
}
```

- `grade`: G1 / G2 / G3 / L / OP / 3勝 / 2勝 / 1勝 / 未勝利 / 新馬
- `surface`: 芝 / ダ
- `going`: 良 / 稍重 / 重 / 不良（前日時点の想定でよい）
- `expected_pace`（任意）: 瞬発 / 持続 / 消耗 / 平均。未指定なら出走馬のテン指数から自動で展開予想する
- `style`（任意）: 逃げ / 先行 / 差し / 追込。近走の `passing` があれば自動判定されるので不要
- `recent`: 近走（新しい順、最大5〜10走）。`horse_id` がありDBに履歴があれば不要
  - `passing`: 通過順（例 "3-3-2-2"）→ 脚質・テン指数の判定に使う
  - `last3f_rank`: そのレースでの上がり3F順位 → 末脚性能
  - `pace_type`: そのレースのラップ型（瞬発/持続/消耗/平均）→ ペース適性
  - `distance`: 距離適性（好走距離の中心・今回距離での成績・延長/短縮）に使う
  - `date`: ローテーション（前走からの間隔・叩き2戦目）に使う
  - `grade` / `jockey` / `weight_carried`: 昇級・降級、乗り替わり、斤量増減に使う
  - `time_sec`: 走破タイム（秒）→ タイム指数。`behind`: 勝ち馬とのタイム差（秒）
- `body_weight_diff`（任意）: 当日の馬体重増減。発表後に入れれば反映される
- `pedigree`（任意）: 5代までの位置キー（S=父, D=母, DS=母父, SS=父の父 …）。クロス・牝系判定に使う
