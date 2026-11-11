"""亀谷『血統の教科書』p106-110 の検証（2026-10-12）.
1) フィリーサイアー/コルトサイアー（keiba.db, 発見2021-23/確認2024/テスト2025-26）: 父ディープ系・ダンチヒ系・ヴァイスリージェント系（デピュティミニスター系）・ステイゴールド系 × 牡/牝/セン × 3歳/4歳以上 × 芝2000以上
2) 新馬戦（data/debut.db, 2023-10〜2024-09 / 2024-10〜2025-09 / 2025-10〜）: ダ1300以下×父米国型/欧州型・日本型、ダ1400以上×父or母父エーピーインディ系/母父ロベルト・ヘイロー・ストームバード・ヴァイスリージェント系/父Dサンデー/父欧州型、
   芝1400以下×父米国型ND系(ダンチヒ・ストームバード・ヴァイスリージェント)・エーピーインディ系/母父サドラーズ・トニービン系、芝1600以上×母父米国型/母父エーピーインディ・ヴァイスリージェント・米国ミスプロ/父米国型/父Dサンデー
A/E＝3着内の実数÷人気から見込む数。使い方: python3 tools/book_ch3e.py → docs/analysis/book_ch3e.md
"""
from __future__ import annotations

import json
import sqlite3
import sys
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from keiba.knowledge import country_type  # noqa: E402

DANZIG = {"デインヒル系", "ウォーフロント系", "グリーンデザート系", "ダンチヒ系"}
STORM = {"ヘネシー系", "テイルオブザキャット系", "ジャイアンツコーズウェイ系", "フォレストリー系", "ハーランズホリデー系", "スキャットダディ系", "ストームキャット系"}
VR = {"デピュティミニスター系"}
US_MISPRO = {"フォーティナイナー系", "ファピアノ系", "シーキングザゴールド系", "ゴーンウエスト系", "スマートストライク系"}
ROBERTO = {"スクリーンヒーロー系", "シンボリクリスエス系", "ブライアンズタイム系", "クリスエス系", "グラスワンダー系"}
HALO = {"ヘイルトゥリーズン系", "サンデーサイレンス系"}
D_SUN = {"ゴールドアリュール系", "ネオユニヴァース系"}


def run(db, per, rows_fn, title):
    c = sqlite3.connect(db)
    base = defaultdict(lambda: [0, 0]); data = []
    for r in c.execute("""select ra.date, ra.surface, ra.distance, r.finish, r.popularity, r.number, r.sex, r.age, h.sire_line, h.damsire_line, ra.payouts, ra.race_id
                          from results r join races ra using(race_id) join horses h using(horse_id)
                          where ra.surface in ('芝','ダ') and r.finish is not null and r.popularity is not null"""):
        p = min(r[4], 14); b = base[p]; b[0] += 1; b[1] += r[3] <= 3
        data.append(r)
    exp = {p: v[1] / v[0] for p, v in base.items()}
    agg = defaultdict(lambda: [[0, 0, 0.0, 0] for _ in range(3)]); pc = {}
    for date, su, dist, fin, pop, num, sex, age, sl, dsl, pay, rid in data:
        if rid not in pc:
            pc[rid] = {cc: y for cc, y in (json.loads(pay).get("複勝", []) if pay else [])}
        for k in rows_fn(su, dist or 1600, sex or "", age, sl, dsl):
            x = agg[k][per(date)]; x[0] += 1; x[1] += fin <= 3; x[2] += exp[min(pop, 14)]; x[3] += pc[rid].get(str(num), 0)
    L = [f"## {title}", "", "| 条件 | 区分 | 走数 | A/E | 複勝回収 |", "|---|---|---|---|---|"]; keep = []
    for k in sorted(agg):
        A = agg[k]
        if min(x[0] for x in A) < 40:
            continue
        ae = [x[1] / x[2] for x in A]
        m = "◎" if min(ae) >= 1.1 else "○" if min(ae) >= 1.05 else "×" if max(ae) <= 0.9 else "▽" if max(ae) <= 0.95 else ""
        L.append(f"| {k[0]} | {m}{k[1]} | " + "/".join(str(x[0]) for x in A) + " | " + "/".join(f"{v:.2f}" for v in ae) + " | " + "/".join(f"{x[3]/x[0]:.0f}" for x in A) + "% |")
        if m:
            keep.append({"title": title, "cond": k[0], "group": k[1], "mark": m, "ae": [round(v, 2) for v in ae]})
    return L + [""], keep


def sex_rows(su, dist, sex, age, sl, dsl):
    s = "牝" if sex.startswith("牝") else "セン" if sex.startswith("セ") else "牡"
    ag = "3歳" if (age or 9) <= 3 else "4歳以上"
    g = []
    if sl == "ディープインパクト系":
        g.append("父ディープ系")
    if sl in DANZIG:
        g.append("父ダンチヒ系")
    if sl in VR:
        g.append("父ヴァイスリージェント系")
    if sl == "ステイゴールド系":
        g.append("父ステイゴールド系")
    out = []
    for x in g:
        out.append((f"{su}・{ag}", f"{x}×{s}"))
        if su == "芝" and dist >= 2000 and ag == "4歳以上":
            out.append(("芝2000以上・4歳以上", f"{x}×{s}"))
    return out


def debut_rows(su, dist, sex, age, sl, dsl):
    st = country_type(sl) if sl else None; dt_ = country_type(dsl) if dsl else None
    out = []
    if su == "ダ" and dist <= 1300:
        cond = "新馬ダ1300以下"
        if st:
            out.append((cond, f"父{st}"))
        if sl in STORM or sl in US_MISPRO:
            out.append((cond, "父ストームバード系/米国ミスプロ系"))
    if su == "ダ" and dist >= 1400:
        cond = "新馬ダ1400以上"
        if sl == "エーピーインディ系" or dsl == "エーピーインディ系":
            out.append((cond, "父か母父エーピーインディ系"))
        if dsl in ROBERTO | HALO | STORM | VR:
            out.append((cond, "母父ロベルト/ヘイロー/ストームバード/ヴァイスリージェント系"))
        if sl in D_SUN:
            out.append((cond, "父Dサンデー"))
        if st:
            out.append((cond, f"父{st}"))
        if dt_ == "欧州型":
            out.append((cond, "母父欧州型"))
    if su == "芝" and dist <= 1400:
        cond = "新馬芝1400以下"
        if sl in DANZIG | STORM | VR or sl == "エーピーインディ系":
            out.append((cond, "父米国型ND系(ダンチヒ/ストームバード/VR)・エーピーインディ系"))
        if dsl in ("サドラーズウェルズ系", "ガリレオ系"):
            out.append((cond, "母父サドラーズウェルズ系"))
        if st:
            out.append((cond, f"父{st}"))
    if su == "芝" and dist >= 1600:
        cond = "新馬芝1600以上"
        if dt_:
            out.append((cond, f"母父{dt_}"))
        if dsl in ("エーピーインディ系",) or dsl in VR or dsl in US_MISPRO:
            out.append((cond, "母父エーピーインディ/ヴァイスリージェント/米国ミスプロ系"))
        if dsl == "ゴーンウエスト系":
            out.append((cond, "母父ゴーンウエスト系"))
        if st:
            out.append((cond, f"父{st}"))
        if sl in D_SUN:
            out.append((cond, "父Dサンデー"))
        if sl == "ステイゴールド系":
            out.append((cond, "父ステイゴールド系"))
    return out


def main():
    L = ["# 亀谷『血統の教科書』p106-110 の検証（自動生成 tools/book_ch3e.py）", "",
         "- A/E＝3着内の実数÷人気から見込む数。◎＝3期間とも1.10以上、○＝1.05以上、×＝0.90以下、▽＝0.95以下。", ""]
    a, k1 = run(ROOT / "data" / "keiba.db", lambda d: 0 if d < "2024-01-01" else 1 if d < "2025-01-01" else 2, sex_rows,
                "牡馬/牝馬が走る血統（各日7R以降, 発見2021-23 / 確認2024 / テスト2025-26）")
    b, k2 = run(ROOT / "data" / "debut.db", lambda d: 0 if d < "2024-10-01" else 1 if d < "2025-10-01" else 2, debut_rows,
                "新馬戦（2023-10〜2024-09 / 2024-10〜2025-09 / 2025-10〜）")
    L += a + b
    (ROOT / "docs" / "analysis" / "book_ch3e.md").write_text("\n".join(L) + "\n", encoding="utf-8")
    (ROOT / "data" / "knowledge" / "book_ch3e.json").write_text(json.dumps({"_meta": "tools/book_ch3e.py", "rows": k1 + k2}, ensure_ascii=False, indent=1), encoding="utf-8")
    print("\n".join(L))


if __name__ == "__main__":
    main()
