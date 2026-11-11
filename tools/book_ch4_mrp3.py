"""第4章 ファピアノ系・その他のミスタープロスペクター系（p164-175）の検証（2026-10-12）.
- 父ファピアノ系: ダ1400-1600 / その他、良（高速）/道悪
- 父エンパイアメーカー系（エンパイアメーカー・バトルプラン・アメリカンファラオ・パイオニアオブザナイル等）: ダートの人気薄、道悪、外枠
- 母系（2〜5代）にファピアノ/アンブライドルズソング × 父サンデー系: 芝・良の短中距離
- 母系にマキャヴェリアン: 芝・良（高速）/道悪
- 父マキャヴェリアン系（ストリートクライ・ストリートセンス等）/父ドバウィ系（マクフィ・モンテロッソ・ニューイヤーズデイ）/父カーリン・アドマイヤドン: 芝/ダ
A/E＝3着内の実数÷人気から見込む数。発見2021-23 / 確認2024 / テスト2025-26。
使い方: python3 tools/book_ch4_mrp3.py <ped5_full.json> → docs/analysis/book_ch4_mrp3.md
"""
import json, sqlite3, sys
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SS = {"ディープインパクト系", "ハーツクライ系", "ステイゴールド系", "フジキセキ系", "ゴールドアリュール系", "ネオユニヴァース系", "アグネスタキオン系",
      "ダイワメジャー系", "ブラックタイド系", "マンハッタンカフェ系", "スペシャルウィーク系", "サンデーサイレンス系"}
EMPIRE = {"エンパイアメーカー", "バトルプラン", "アメリカンファラオ", "パイオニアオブザナイル", "Pioneerof the Nile", "American Pharoah", "Empire Maker"}
DUBAWI = {"マクフィ", "モンテロッソ", "ニューイヤーズデイ", "ドバウィ", "Dubawi"}


def per(d):
    return 0 if d < "2024-01-01" else 1 if d < "2025-01-01" else 2


def main(path):
    P = json.loads(Path(path).read_text(encoding="utf-8")); pos = P["pos"]; H = P["horses"]
    c = sqlite3.connect(ROOT / "data" / "keiba.db")
    base = defaultdict(lambda: [0, 0]); rows = []
    for date, su, dist, going, hid, fin, pop, num, sire, sl, pay in c.execute(
            """select ra.date, ra.surface, ra.distance, ra.going, r.horse_id, r.finish, r.popularity, r.number, h.sire, h.sire_line, ra.payouts
               from results r join races ra using(race_id) join horses h using(horse_id)
               where ra.surface in ('芝','ダ') and r.finish is not null and r.popularity is not null"""):
        p = min(pop, 14); b = base[p]; b[0] += 1; b[1] += fin <= 3
        rows.append((date, su, dist or 1600, going or "良", hid, fin, p, num, sire, sl, pay))
    exp = {p: v[1] / v[0] for p, v in base.items()}
    agg = defaultdict(lambda: [[0, 0, 0.0, 0, 0] for _ in range(3)]); pc = {}
    for date, su, dist, going, hid, fin, p, num, sire, sl, pay in rows:
        if pay not in pc:
            j = json.loads(pay) if pay else {}
            pc[pay] = ({cc: y for cc, y in j.get("複勝", [])}, {cc: y for cc, y in j.get("単勝", [])})
        fk, tk = pc[pay][0].get(str(num), 0), pc[pay][1].get(str(num), 0)
        good = going.startswith("良")
        dam = set(n for k, n in zip(pos, H.get(hid) or []) if n and k.startswith("D"))
        K = []
        if sl == "ファピアノ系":
            K += [("父ファピアノ系", f"{su}・{'1400-1600' if 1400 <= dist <= 1600 else 'その他の距離'}"), ("父ファピアノ系", f"{su}・{'良' if good else '道悪'}")]
        if sire in EMPIRE and su == "ダ":
            K += [("父エンパイアメーカー系", f"ダ・{'6番人気以下' if p >= 6 else '5番人気以内'}"), ("父エンパイアメーカー系", f"ダ・{'良' if good else '道悪'}"),
                  ("父エンパイアメーカー系", f"ダ・{'2桁馬番' if num >= 10 else '1桁馬番'}")]
        if sl in SS and su == "芝" and dam & {"Fappiano", "ファピアノ", "Unbridled's Song", "アンブライドルズソング", "Unbridled", "アンブライドルド"}:
            K.append(("父サンデー系×母系にファピアノ系", f"芝・{'良' if good else '道悪'}・{'〜1800' if dist <= 1800 else '2000〜'}"))
        if su == "芝" and dam & {"Machiavellian", "マキャヴェリアン"}:
            K.append(("母系にマキャヴェリアン", f"芝・{'良' if good else '道悪'}"))
        if sl == "マキャヴェリアン系":
            K.append(("父マキャヴェリアン系", su))
        if sire in DUBAWI:
            K.append(("父ドバウィ系", su))
        if sire in ("カーリン", "アドマイヤドン"):
            K.append((f"父{sire}", su))
        for k in K:
            x = agg[k][per(date)]; x[0] += 1; x[1] += fin <= 3; x[2] += exp[p]; x[3] += fk; x[4] += tk
    L = ["# 第4章 ファピアノ系・その他のミスプロ系（p164-175）の検証（自動生成 tools/book_ch4_mrp3.py）", "",
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
    (ROOT / "docs" / "analysis" / "book_ch4_mrp3.md").write_text("\n".join(L) + "\n", encoding="utf-8")
    print("\n".join(L))


if __name__ == "__main__":
    main(sys.argv[1])
