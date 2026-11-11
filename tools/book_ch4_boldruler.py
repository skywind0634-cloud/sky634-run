"""第4章 ボールドルーラー系・レッドゴッド系・ネヴァーベンド系（p126-137）の検証（2026-10-12）.
- 父エーピーインディ系: ダート全体（父サンデー系と回収率比較）、東京ダ1300-1600、ダ直線長/短、左回り/右回り、ダ1700、良/道悪
- 種牡馬別: シニスターミニスター（ダート・人気薄）、パイロ（ダ1200-1400×2-3歳 / 4歳以上）、カジノドライヴ（左回り・直線長・1700）、
  マジェスティックウォリアー、カリフォルニアクローム、バゴ（芝1200・芝2000 / その他）
- 母父エーピーインディ系: ダート
- 5代にセクレタリアト: 芝・良（高速）/道悪、ブラッシンググルーム: 芝・道悪、ミルリーフ: 芝・道悪/実際の消耗ペース、リヴァーマン: 芝・阪神中山/その他
A/E＝3着内の実数÷人気から見込む数。発見2021-23 / 確認2024 / テスト2025-26。
使い方: python3 tools/book_ch4_boldruler.py <ped5_full.json> → docs/analysis/book_ch4_boldruler.md
"""
from __future__ import annotations

import json
import sqlite3
import sys
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SS = {"ディープインパクト系", "ハーツクライ系", "ステイゴールド系", "フジキセキ系", "ゴールドアリュール系", "ネオユニヴァース系", "アグネスタキオン系",
      "ダイワメジャー系", "ブラックタイド系", "マンハッタンカフェ系", "スペシャルウィーク系", "サンデーサイレンス系"}
LEFT = {"東京", "中京", "新潟"}
LONG_D = {"東京", "中京"}


def per(d):
    return 0 if d < "2024-01-01" else 1 if d < "2025-01-01" else 2


def main(pedpath):
    H = json.loads(Path(pedpath).read_text(encoding="utf-8"))["horses"]
    c = sqlite3.connect(ROOT / "data" / "keiba.db")
    base = defaultdict(lambda: [0, 0]); rows = []
    for date, co, su, dist, going, pt, hid, fin, pop, num, age, sire, sl, dsl, pay in c.execute(
            """select ra.date, ra.course, ra.surface, ra.distance, ra.going, ra.pace_type, r.horse_id, r.finish, r.popularity, r.number, r.age,
                      h.sire, h.sire_line, h.damsire_line, ra.payouts
               from results r join races ra using(race_id) join horses h using(horse_id)
               where ra.surface in ('芝','ダ') and r.finish is not null and r.popularity is not null"""):
        p = min(pop, 14); b = base[p]; b[0] += 1; b[1] += fin <= 3
        rows.append((date, co, su, dist or 1600, going or "良", pt, hid, fin, p, num, age, sire, sl, dsl, pay))
    exp = {p: v[1] / v[0] for p, v in base.items()}
    agg = defaultdict(lambda: [[0, 0, 0.0, 0, 0] for _ in range(3)]); pc = {}
    for date, co, su, dist, going, pt, hid, fin, p, num, age, sire, sl, dsl, pay in rows:
        if pay not in pc:
            j = json.loads(pay) if pay else {}
            pc[pay] = ({cc: y for cc, y in j.get("複勝", [])}, {cc: y for cc, y in j.get("単勝", [])})
        fk, tk = pc[pay][0].get(str(num), 0), pc[pay][1].get(str(num), 0); pr = per(date)
        good = going.startswith("良"); names = set(n for n in (H.get(hid) or []) if n)
        K = []
        if su == "ダ":
            if sl == "エーピーインディ系":
                K += [("父エーピーインディ系", "ダ全体"), ("父エーピーインディ系", f"ダ・直線{'長' if co in LONG_D else '短'}"),
                      ("父エーピーインディ系", f"ダ・{'左回り' if co in LEFT else '右回り'}"), ("父エーピーインディ系", f"ダ・{'良' if good else '道悪'}")]
                if co == "東京" and 1300 <= dist <= 1600:
                    K.append(("父エーピーインディ系", "東京ダ1300-1600"))
                if dist == 1700:
                    K.append(("父エーピーインディ系", "ダ1700"))
                if p >= 6:
                    K.append(("父エーピーインディ系", "ダ・6番人気以下"))
            if sl in SS:
                K.append(("父サンデー系（比較）", "ダ全体"))
            if dsl == "エーピーインディ系":
                K.append(("母父エーピーインディ系", "ダ全体"))
            if sire == "シニスターミニスター":
                K += [("シニスターミニスター", "ダ全体"), ("シニスターミニスター", "ダ・6番人気以下" if p >= 6 else "ダ・5番人気以内")]
            if sire == "パイロ" and dist <= 1400:
                K.append(("パイロ", f"ダ1400以下・{'2-3歳' if (age or 9) <= 3 else '4歳以上'}"))
            if sire == "カジノドライヴ":
                K += [("カジノドライヴ", f"ダ・{'左回り' if co in LEFT else '右回り'}")] + ([("カジノドライヴ", "ダ1700")] if dist == 1700 else [])
            if sire in ("マジェスティックウォリアー", "カリフォルニアクローム"):
                K.append((sire, f"ダ・直線{'長' if co in LONG_D else '短'}"))
        else:
            if sire == "バゴ":
                K.append(("バゴ", "芝1200・芝2000" if dist in (1200, 2000) else "芝その他"))
            if names & {"Secretariat", "セクレタリアト"}:
                K.append(("5代にセクレタリアト", f"芝・{'良' if good else '道悪'}"))
            if names & {"Blushing Groom", "ブラッシンググルーム"}:
                K.append(("5代にブラッシンググルーム", f"芝・{'良' if good else '道悪'}"))
            if names & {"Mill Reef", "ミルリーフ"}:
                K.append(("5代にミルリーフ", f"芝・{'良' if good else '道悪'}"))
                if pt:
                    K.append(("5代にミルリーフ", f"芝・実際のペース{pt}"))
            if names & {"Riverman", "リヴァーマン"}:
                K.append(("5代にリヴァーマン", "芝・阪神中山" if co in ("阪神", "中山") else "芝・その他"))
        for k in K:
            x = agg[k][pr]; x[0] += 1; x[1] += fin <= 3; x[2] += exp[p]; x[3] += fk; x[4] += tk
    L = ["# 第4章 ボールドルーラー系・レッドゴッド系・ネヴァーベンド系（p126-137）の検証（自動生成 tools/book_ch4_boldruler.py）", "",
         "- A/E＝3着内の実数÷人気から見込む数。発見2021-23 / 確認2024 / テスト2025-26。◎＝3期間とも1.10以上、○＝1.05以上、×＝0.90以下、▽＝0.95以下。", "",
         "| 血統 | 条件 | 走数 | A/E | 複勝回収 | 単勝回収 |", "|---|---|---|---|---|---|"]
    keep = []
    for k in sorted(agg):
        A = agg[k]
        if min(x[0] for x in A) < 40:
            continue
        ae = [x[1] / x[2] for x in A]
        m = "◎" if min(ae) >= 1.1 else "○" if min(ae) >= 1.05 else "×" if max(ae) <= 0.9 else "▽" if max(ae) <= 0.95 else ""
        L.append(f"| {k[0]} | {m}{k[1]} | " + "/".join(str(x[0]) for x in A) + " | " + "/".join(f"{v:.2f}" for v in ae) + " | "
                 + "/".join(f"{x[3]/x[0]:.0f}" for x in A) + "% | " + "/".join(f"{x[4]/x[0]:.0f}" for x in A) + "% |")
        if m:
            keep.append({"blood": k[0], "cond": k[1], "mark": m, "ae": [round(v, 2) for v in ae]})
    (ROOT / "docs" / "analysis" / "book_ch4_boldruler.md").write_text("\n".join(L) + "\n", encoding="utf-8")
    (ROOT / "data" / "knowledge" / "book_ch4_boldruler.json").write_text(json.dumps({"_meta": "tools/book_ch4_boldruler.py", "rows": keep}, ensure_ascii=False, indent=1), encoding="utf-8")
    print("\n".join(L))


if __name__ == "__main__":
    main(sys.argv[1])
