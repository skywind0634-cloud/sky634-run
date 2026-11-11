"""第4章 ミスタープロスペクター系（p150-163）の本の主張の検証（2026-10-12）.
- キングマンボ系/キンカメ: 芝の内枠（1-3枠）、距離延長、極端なペース（実際の瞬発/消耗）
- ルーラーシップ: 芝1400以下の人気馬（1-3番人気）、ダ1200以下、芝2200以上
- ロードカナロア: 芝1200以下、ダート
- フォーティナイナー系: ダ1200以下・芝1200以下
- サウスヴィグラス: ダ1200以下の人気馬/人気薄、前走10着以下
- アドマイヤムーン: 芝1200
- アイルハヴアナザー: ダ1800、ダートで前走1600以下から延長、前走芝、中山ダ1800、牝馬1200以下、牡馬ダ1200の人気薄
A/E＝3着内の実数÷人気から見込む数。発見2021-23 / 確認2024 / テスト2025-26。
使い方: python3 tools/book_ch4_mrp2.py → docs/analysis/book_ch4_mrp2.md
"""
import json, sqlite3
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
KM = {"キングカメハメハ系", "キングマンボ系"}


def per(d):
    return 0 if d < "2024-01-01" else 1 if d < "2025-01-01" else 2


def main():
    c = sqlite3.connect(ROOT / "data" / "keiba.db")
    base = defaultdict(lambda: [0, 0]); rows = []
    for date, co, su, dist, pt, hid, fin, pop, num, gate, sex, sire, sl, pay in c.execute(
            """select ra.date, ra.course, ra.surface, ra.distance, ra.pace_type, r.horse_id, r.finish, r.popularity, r.number, r.gate, r.sex,
                      h.sire, h.sire_line, ra.payouts
               from results r join races ra using(race_id) join horses h using(horse_id)
               where ra.surface in ('芝','ダ') and r.finish is not null and r.popularity is not null order by ra.date, ra.race_id"""):
        p = min(pop, 14); b = base[p]; b[0] += 1; b[1] += fin <= 3
        rows.append((date, co, su, dist or 1600, pt, hid, fin, p, pop, num, gate, sex or "", sire, sl, pay))
    exp = {p: v[1] / v[0] for p, v in base.items()}
    agg = defaultdict(lambda: [[0, 0, 0.0, 0, 0] for _ in range(3)]); pc = {}; last = {}
    for date, co, su, dist, pt, hid, fin, p, pop, num, gate, sex, sire, sl, pay in rows:
        prev = last.get(hid); last[hid] = (su, dist, fin)
        if pay not in pc:
            j = json.loads(pay) if pay else {}
            pc[pay] = ({cc: y for cc, y in j.get("複勝", [])}, {cc: y for cc, y in j.get("単勝", [])})
        fk, tk = pc[pay][0].get(str(num), 0), pc[pay][1].get(str(num), 0)
        K = []
        if sl in KM and su == "芝":
            if gate:
                K.append(("父キングマンボ系", f"芝・{'内枠1-3' if gate <= 3 else '外枠6-8' if gate >= 6 else '中枠4-5'}"))
            if prev and prev[0] == "芝" and dist >= prev[1] + 200:
                K.append(("父キングマンボ系", "芝・距離延長"))
            if pt:
                K.append(("父キングマンボ系", f"芝・実際のペース{pt}"))
        if sire == "キングカメハメハ" and su == "芝" and gate:
            K.append(("キングカメハメハ", f"芝・{'内枠1-3' if gate <= 3 else 'その他の枠'}"))
        if sire == "ルーラーシップ":
            if su == "芝" and dist <= 1400:
                K.append(("ルーラーシップ", f"芝1400以下・{'1-3番人気' if pop <= 3 else '4番人気以下'}"))
            if su == "ダ" and dist <= 1200:
                K.append(("ルーラーシップ", "ダ1200以下"))
            if su == "芝" and dist >= 2200:
                K.append(("ルーラーシップ", "芝2200以上"))
        if sire == "ロードカナロア":
            K.append(("ロードカナロア", "芝1200以下" if su == "芝" and dist <= 1200 else "ダート" if su == "ダ" else "芝1400以上"))
        if sl == "フォーティナイナー系" and dist <= 1200:
            K.append(("父フォーティナイナー系", f"{su}1200以下"))
        if sire == "サウスヴィグラス" and su == "ダ" and dist <= 1200:
            K.append(("サウスヴィグラス", f"ダ1200以下・{'1-3番人気' if pop <= 3 else '4番人気以下'}"))
            if prev and (prev[2] or 0) >= 10:
                K.append(("サウスヴィグラス", "ダ1200以下・前走10着以下"))
        if sire == "アドマイヤムーン" and su == "芝":
            K.append(("アドマイヤムーン", "芝1200" if dist == 1200 else "芝その他"))
        if sire == "アイルハヴアナザー" and su == "ダ":
            K.append(("アイルハヴアナザー", "ダ1800" if dist == 1800 else "ダその他"))
            if prev and prev[0] == "ダ" and prev[1] <= 1600 and dist >= prev[1] + 200:
                K.append(("アイルハヴアナザー", "ダ・前走1600以下から延長"))
            if prev and prev[0] == "芝":
                K.append(("アイルハヴアナザー", "ダ・前走芝"))
            if dist <= 1200:
                K.append(("アイルハヴアナザー", f"ダ1200以下・{'牝' if sex.startswith('牝') else '牡セ'}"))
        for k in K:
            x = agg[k][per(date)]; x[0] += 1; x[1] += fin <= 3; x[2] += exp[p]; x[3] += fk; x[4] += tk
    L = ["# 第4章 ミスタープロスペクター系（p150-163）の本の主張の検証（自動生成 tools/book_ch4_mrp2.py）", "",
         "- A/E＝3着内の実数÷人気から見込む数。発見2021-23 / 確認2024 / テスト2025-26。◎＝3期間とも1.10以上、○＝1.05以上、×＝0.90以下、▽＝0.95以下。", "",
         "| 血統 | 条件 | 走数 | A/E | 複勝回収 | 単勝回収 |", "|---|---|---|---|---|---|"]
    for k in sorted(agg):
        A = agg[k]
        if min(x[0] for x in A) < 30:
            continue
        ae = [x[1] / x[2] for x in A]
        m = "◎" if min(ae) >= 1.1 else "○" if min(ae) >= 1.05 else "×" if max(ae) <= 0.9 else "▽" if max(ae) <= 0.95 else ""
        L.append(f"| {k[0]} | {m}{k[1]} | " + "/".join(str(x[0]) for x in A) + " | " + "/".join(f"{v:.2f}" for v in ae) + " | "
                 + "/".join(f"{x[3]/x[0]:.0f}" for x in A) + "% | " + "/".join(f"{x[4]/x[0]:.0f}" for x in A) + "% |")
    (ROOT / "docs" / "analysis" / "book_ch4_mrp2.md").write_text("\n".join(L) + "\n", encoding="utf-8")
    print("\n".join(L))


if __name__ == "__main__":
    main()
