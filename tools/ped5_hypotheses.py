"""5代血統表で、JRA研修資料「サラブレッドの血統」（2023年3月FC研修）の仮説を検証する（2026-10-11）.

1. 名牝（牝馬）のインブリード: 5代以内に同じ牝馬が2回以上（例: スペシャル≒リサデル, Natalma …）
2. アルマームードのクロス: Natalma（ノーザンダンサーの母）と Cosmah（ヘイローの母）が両方5代以内にいる（全姉妹の母アルマームードのクロス）
3. X染色体: 牡馬は「母・母の父」、牝馬はさらに「父の母」の系統が効く → 父母父（SDS）・母母父（DDS）の国別タイプ別 A/E を牡牝で比較
4. 濃い牡馬クロス（3×3以内など）と、クロスなし（アウトブリード）
評価: 3着内の人気からの期待比（A/E）と複勝回収率。発見＝〜2023 / テスト＝2024〜。データ: data/ped5_full.json（tools/ped5_full.py）。

使い方: python3 tools/ped5_hypotheses.py [ped5_full.json] → docs/analysis/ped5_hypotheses.md
"""
from __future__ import annotations

import json
import sqlite3
import sys
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from keiba.knowledge import country_type  # noqa: E402

OUT = ROOT / "docs" / "analysis" / "ped5_hypotheses.md"


def sire_type_of(name: str, line_of: dict) -> str | None:
    ln = line_of.get(name)
    return country_type(ln) if ln else None


def main(path: str):
    P = json.loads(Path(path).read_text(encoding="utf-8"))
    pos, H = P["pos"], P["horses"]
    gen = {p: len(p) for p in pos}
    c = sqlite3.connect(ROOT / "data" / "keiba.db")
    # 種牡馬名 → 系統（DB の父・母父の系統から）
    line_of = {}
    for s, sl in c.execute("select sire, sire_line from horses where sire_line is not null"):
        line_of.setdefault(s, sl)
    for s, sl in c.execute("select damsire, damsire_line from horses where damsire_line is not null"):
        line_of.setdefault(s, sl)
    feats = {}
    for hid, names in H.items():
        a = dict(zip(pos, names))
        f = {}
        mares = Counter(n for p, n in a.items() if n and p.endswith("D"))
        stallions = Counter(n for p, n in a.items() if n and p.endswith("S"))
        f["名牝クロスあり"] = any(v >= 2 for v in mares.values())
        f["アルマームードのクロス（Natalma＋Cosmah）"] = "Natalma" in mares and "Cosmah" in mares
        best = 99
        for nm, v in stallions.items():
            if v >= 2:
                gs = sorted(gen[p] for p, n in a.items() if n == nm)
                best = min(best, gs[0] + gs[1])
        f["牡馬クロス 3×3以内"] = best <= 6
        f["クロスなし（5代以内）"] = best == 99 and not f["名牝クロスあり"]
        f["SDS"] = sire_type_of(a.get("SDS", ""), line_of)
        f["DDS"] = sire_type_of(a.get("DDS", ""), line_of)
        feats[hid] = f
    base = defaultdict(lambda: [0, 0])
    rows = []
    for hid, sex, fin, pop, num, pay, date in c.execute(
            """select r.horse_id, h.sex, r.finish, r.popularity, r.number, ra.payouts, ra.date from results r
               join races ra using(race_id) join horses h using(horse_id) where r.finish is not null and r.popularity is not null"""):
        p = min(pop, 14); b = base[p]; b[0] += 1; b[1] += fin <= 3
        if hid in feats:
            fk = 0
            if pay:
                for cc, y in json.loads(pay).get("複勝", []):
                    if cc == str(num):
                        fk = y
            rows.append((hid, sex, fin <= 3, p, fk, "発見" if date < "2024-01-01" else "テスト"))
    exp = {p: v[1] / v[0] for p, v in base.items()}
    agg = defaultdict(lambda: [0, 0, 0.0, 0])
    for hid, sex, top, p, fk, per in rows:
        f = feats[hid]; sx = "牝" if sex and sex.startswith("牝") else "牡・セ"
        keys = [(k, "あり") for k in f if isinstance(f[k], bool) and f[k]]
        for k in ("SDS", "DDS"):
            if f[k]:
                keys.append((f"{'父母父' if k == 'SDS' else '母母父'}のタイプ×{sx}", f[k]))
        for k in keys:
            a = agg[(k, per)]; a[0] += 1; a[1] += top; a[2] += exp[p]; a[3] += fk
    L = ["# 5代血統表での仮説検証（JRA研修資料「サラブレッドの血統」, 自動生成 tools/ped5_hypotheses.py）", "",
         f"- 5代血統表のある馬 {len(H)} 頭・延べ {len(rows)} 走。A/E＝3着内の実数÷人気から見込む数（1.00が人気どおり）。発見＝〜2023 / テスト＝2024〜。", "",
         "| 特徴 | 値 | 走数 発見/テスト | A/E 発見/テスト | 複勝回収 発見/テスト |", "|---|---|--:|--:|--:|"]
    for k in sorted({k for k, _ in agg}):
        a, b = agg.get((k, "発見")), agg.get((k, "テスト"))
        if not a or not b or a[0] < 100 or b[0] < 100:
            continue
        L.append(f"| {k[0]} | {k[1]} | {a[0]}/{b[0]} | {a[1]/a[2]:.2f} / {b[1]/b[2]:.2f} | {a[3]/a[0]:.0f}% / {b[3]/b[0]:.0f}% |")
    OUT.write_text("\n".join(L) + "\n", encoding="utf-8")
    print("\n".join(L))


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else str(ROOT / "data" / "ped5_full.json"))
