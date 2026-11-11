"""第4章 ミスプロ系その他II・ヘイロー系（p176-185）の検証（2026-10-12）. 父または母父として:
アグネスデジタル（ダート・不良/重、ダ1800）、アフリート（ダート）、スキャン（東京ダート）、ジェイドロバリー（ダ1400-1600）、アルデバランⅡ（芝）、
タイキシャトル（芝マイル）、メイショウボーラー（ダ1400、牡のダ1700以上の穴、芝）、ロージズインメイ（上がりのかかるレース）。
A/E＝3着内の実数÷人気から見込む数。発見2021-23 / 確認2024 / テスト2025-26。
使い方: python3 tools/book_ch4_halo.py → docs/analysis/book_ch4_halo.md
"""
import json, sqlite3
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
NAMES = ["アグネスデジタル", "アフリート", "スキャン", "ジェイドロバリー", "アルデバランII", "タイキシャトル", "メイショウボーラー", "ロージズインメイ", "ドリームバレンチノ"]


def per(d):
    return 0 if d < "2024-01-01" else 1 if d < "2025-01-01" else 2


def main():
    c = sqlite3.connect(ROOT / "data" / "keiba.db")
    base = defaultdict(lambda: [0, 0]); rows = []
    for date, co, su, dist, going, l3, hid, fin, pop, num, sex, sire, ds, pay in c.execute(
            """select ra.date, ra.course, ra.surface, ra.distance, ra.going, ra.last3f, r.horse_id, r.finish, r.popularity, r.number, r.sex,
                      h.sire, h.damsire, ra.payouts
               from results r join races ra using(race_id) join horses h using(horse_id)
               where ra.surface in ('芝','ダ') and r.finish is not null and r.popularity is not null"""):
        p = min(pop, 14); b = base[p]; b[0] += 1; b[1] += fin <= 3
        rows.append((date, co, su, dist or 1600, going or "良", l3, hid, fin, p, num, sex or "", sire, ds, pay))
    exp = {p: v[1] / v[0] for p, v in base.items()}
    l3m = defaultdict(list)
    for r in rows:
        if r[5]:
            l3m[(r[2], r[3] // 200)].append(r[5])
    med = {k: sorted(v)[len(v) // 2] for k, v in l3m.items()}
    agg = defaultdict(lambda: [[0, 0, 0.0, 0] for _ in range(3)]); pc = {}
    for date, co, su, dist, going, l3, hid, fin, p, num, sex, sire, ds, pay in rows:
        if pay not in pc:
            pc[pay] = {cc: y for cc, y in (json.loads(pay).get("複勝", []) if pay else [])}
        fk = pc[pay].get(str(num), 0)
        for who, nm in (("父", sire), ("母父", ds)):
            if nm not in NAMES and not (nm or "").startswith("アルデバラン"):
                continue
            nm = "アルデバランII" if (nm or "").startswith("アルデバラン") else nm
            conds = [su, f"{su}・{'良' if going.startswith('良') else '道悪'}",
                     f"{su}・{'〜1400' if dist <= 1400 else '1600-1800' if dist <= 1800 else '2000〜'}"]
            if su == "ダ" and co == "東京":
                conds.append("東京ダ")
            if l3 and (su, dist // 200) in med:
                conds.append(f"{su}・上がり{'かかる' if l3 > med[(su, dist // 200)] else '速い'}")
            if su == "ダ" and dist >= 1700 and not sex.startswith("牝") and p >= 6:
                conds.append("ダ1700以上・牡セ・6番人気以下")
            for cd in conds:
                x = agg[(f"{who}{nm}", cd)][per(date)]; x[0] += 1; x[1] += fin <= 3; x[2] += exp[p]; x[3] += fk
    L = ["# 第4章 ミスプロ系その他II・ヘイロー系（p176-185）の検証（自動生成 tools/book_ch4_halo.py）", "",
         "- A/E＝3着内の実数÷人気から見込む数。発見2021-23 / 確認2024 / テスト2025-26。◎＝3期間とも1.10以上、○＝1.05以上、×＝0.90以下、▽＝0.95以下。", "",
         "| 血統 | 条件 | 走数 | A/E | 複勝回収 |", "|---|---|---|---|---|"]
    for k in sorted(agg):
        A = agg[k]
        if min(x[0] for x in A) < 30:
            continue
        ae = [x[1] / x[2] for x in A]
        m = "◎" if min(ae) >= 1.1 else "○" if min(ae) >= 1.05 else "×" if max(ae) <= 0.9 else "▽" if max(ae) <= 0.95 else ""
        L.append(f"| {k[0]} | {m}{k[1]} | " + "/".join(str(x[0]) for x in A) + " | " + "/".join(f"{v:.2f}" for v in ae) + " | " + "/".join(f"{x[3]/x[0]:.0f}" for x in A) + "% |")
    (ROOT / "docs" / "analysis" / "book_ch4_halo.md").write_text("\n".join(L) + "\n", encoding="utf-8")
    print("\n".join(L))


if __name__ == "__main__":
    main()
