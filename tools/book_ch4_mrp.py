"""第4章 ミスタープロスペクター系の先行検証（2026-10-12）: ミスプロ系の主要種牡馬（産駒200走以上）× レース条件で、
発見2021-23 / 確認2024 / テスト2025-26 の3期間とも A/E 1.10以上（○）/0.90以下（▼）のもの（各期間40走以上）。
条件: 芝ダ・距離帯・良/道悪・坂/平坦・直線長/短・2-3歳/4歳以上・牡/牝・距離延長/短縮・休み明け・OP以上。
使い方: python3 tools/book_ch4_mrp.py → docs/analysis/book_ch4_mrp.md, data/knowledge/book_ch4_mrp.json
"""
import datetime as dt
import json
import sqlite3
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MISPRO = {"キングカメハメハ系", "キングマンボ系", "フォーティナイナー系", "ファピアノ系", "シーキングザゴールド系", "ゴーンウエスト系", "マキャヴェリアン系",
          "スマートストライク系", "ミスタープロスペクター系"}
SLOPE = {"中山", "阪神", "中京", "東京"}
LONG = {"東京", "新潟", "阪神", "京都", "中京"}
OPEN = {"OP", "L", "G3", "G2", "G1"}


def per(d):
    return 0 if d < "2024-01-01" else 1 if d < "2025-01-01" else 2


def main():
    c = sqlite3.connect(ROOT / "data" / "keiba.db")
    base = defaultdict(lambda: [0, 0]); rows = []
    for date, co, su, dist, going, grade, hid, fin, pop, num, age, sex, sire, sl, pay in c.execute(
            """select ra.date, ra.course, ra.surface, ra.distance, ra.going, ra.grade, r.horse_id, r.finish, r.popularity, r.number, r.age, r.sex,
                      h.sire, h.sire_line, ra.payouts
               from results r join races ra using(race_id) join horses h using(horse_id)
               where ra.surface in ('芝','ダ') and r.finish is not null and r.popularity is not null order by ra.date, ra.race_id"""):
        p = min(pop, 14); b = base[p]; b[0] += 1; b[1] += fin <= 3
        rows.append((date, co, su, dist or 1600, going or "良", grade, hid, fin, p, num, age, sex or "", sire, sl, pay))
    exp = {p: v[1] / v[0] for p, v in base.items()}
    agg = defaultdict(lambda: [[0, 0, 0.0, 0, 0] for _ in range(3)]); pc = {}; last = {}
    for date, co, su, dist, going, grade, hid, fin, p, num, age, sex, sire, sl, pay in rows:
        prev = last.get(hid); last[hid] = (date, dist)
        if sl not in MISPRO or not sire:
            continue
        if pay not in pc:
            j = json.loads(pay) if pay else {}
            pc[pay] = ({cc: y for cc, y in j.get("複勝", [])}, {cc: y for cc, y in j.get("単勝", [])})
        fk, tk = pc[pay][0].get(str(num), 0), pc[pay][1].get(str(num), 0)
        bd = (("芝〜1400" if dist <= 1400 else "芝1600-1800" if dist <= 1800 else "芝2000-2400" if dist <= 2400 else "芝2500〜") if su == "芝"
              else ("ダ〜1400" if dist <= 1400 else "ダ1600-1900" if dist <= 1900 else "ダ2000〜"))
        conds = [su, bd, f"{su}・{'良' if going.startswith('良') else '道悪'}", f"{su}・{'坂' if co in SLOPE else '平坦'}",
                 f"{su}・直線{'長' if co in LONG else '短'}", f"{su}・{'2-3歳' if (age or 9) <= 3 else '4歳以上'}",
                 f"{su}・{'牝' if sex.startswith('牝') else '牡セ'}", f"{co}{su}"]
        if grade in OPEN:
            conds.append(f"{su}・OP以上")
        if prev:
            if abs(dist - prev[1]) >= 200:
                conds.append(f"{su}・{'延長' if dist > prev[1] else '短縮'}")
            if (dt.date.fromisoformat(date) - dt.date.fromisoformat(prev[0])).days >= 63:
                conds.append(f"{su}・休み明け")
        for who in (sire, sl):
            for cd in conds:
                x = agg[(who, cd)][per(date)]; x[0] += 1; x[1] += fin <= 3; x[2] += exp[p]; x[3] += fk; x[4] += tk
    out = []
    for (who, cd), A in agg.items():
        if min(x[0] for x in A) < 40:
            continue
        ae = [x[1] / x[2] for x in A]
        if min(ae) >= 1.10 or max(ae) <= 0.90:
            out.append({"sire": who, "cond": cd, "mark": "○" if min(ae) >= 1.1 else "▼", "ae": [round(v, 2) for v in ae],
                        "fuku": [round(x[3] / x[0]) for x in A], "tan": [round(x[4] / x[0]) for x in A], "n": [x[0] for x in A]})
    out.sort(key=lambda o: (o["sire"], o["mark"], o["cond"]))
    (ROOT / "data" / "knowledge" / "book_ch4_mrp.json").write_text(json.dumps({"_meta": "tools/book_ch4_mrp.py", "rows": out}, ensure_ascii=False, indent=1), encoding="utf-8")
    L = ["# ミスタープロスペクター系の種牡馬 × 条件（3期間とも人気以上○/以下▼, 自動生成 tools/book_ch4_mrp.py）", "",
         "- A/E＝3着内の実数÷人気から見込む数。発見2021-23 / 確認2024 / テスト2025-26（各40走以上）。", "",
         "| 種牡馬/系統 | 条件 | | A/E | 複勝回収 | 単勝回収 | 走数 |", "|---|---|---|---|---|---|---|"]
    for o in out:
        L.append(f"| {o['sire']} | {o['cond']} | {o['mark']} | " + "/".join(f"{v:.2f}" for v in o["ae"]) + " | " + "/".join(map(str, o["fuku"])) + "% | "
                 + "/".join(map(str, o["tan"])) + "% | " + "/".join(map(str, o["n"])) + " |")
    (ROOT / "docs" / "analysis" / "book_ch4_mrp.md").write_text("\n".join(L) + "\n", encoding="utf-8")
    print("\n".join(L))


if __name__ == "__main__":
    main()
