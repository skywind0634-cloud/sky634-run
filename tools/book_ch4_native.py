"""第4章 ネヴァーセイダイ系・ネイティヴダンサー系・レイズアネイティヴ系（p136-149）の検証（2026-10-12）.
本ではいずれも父系はほぼ途絶え、母系に入って影響する血。5代血統表に以下を持つ馬の 芝/ダ・良/道悪・距離帯 の A/E。
ネヴァービート / シャーペンアップ（エタン系: スタミナ・成長力） / アファームド / アリダー / ブレイヴェストローマン（ダート・牝馬の芝）/ シーバード
使い方: python3 tools/book_ch4_native.py <ped5_full.json> → docs/analysis/book_ch4_native.md
"""
import json, sqlite3, sys
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ANC = {"ネヴァービート": {"Never Beat", "ネヴァービート"}, "シャーペンアップ": {"Sharpen Up", "シャーペンアップ"},
       "アファームド": {"Affirmed", "アファームド"}, "アリダー": {"Alydar", "アリダー"},
       "ブレイヴェストローマン": {"Bravest Roman", "ブレイヴェストローマン"}, "シーバード": {"Sea-Bird", "Sea Bird", "シーバード"}}


def per(d):
    return 0 if d < "2024-01-01" else 1 if d < "2025-01-01" else 2


def main(path):
    H = json.loads(Path(path).read_text(encoding="utf-8"))["horses"]
    c = sqlite3.connect(ROOT / "data" / "keiba.db")
    base = defaultdict(lambda: [0, 0]); rows = []
    for date, su, dist, going, sex, hid, fin, pop, num, pay in c.execute(
            """select ra.date, ra.surface, ra.distance, ra.going, r.sex, r.horse_id, r.finish, r.popularity, r.number, ra.payouts
               from results r join races ra using(race_id) where ra.surface in ('芝','ダ') and r.finish is not null and r.popularity is not null"""):
        p = min(pop, 14); b = base[p]; b[0] += 1; b[1] += fin <= 3
        rows.append((date, su, dist or 1600, going or "良", sex or "", hid, fin, p, num, pay))
    exp = {p: v[1] / v[0] for p, v in base.items()}
    agg = defaultdict(lambda: [[0, 0, 0.0, 0] for _ in range(3)]); pc = {}
    for date, su, dist, going, sex, hid, fin, p, num, pay in rows:
        names = set(n for n in (H.get(hid) or []) if n)
        if not names:
            continue
        if pay not in pc:
            pc[pay] = {cc: y for cc, y in (json.loads(pay).get("複勝", []) if pay else [])}
        fk = pc[pay].get(str(num), 0); pr = per(date)
        conds = [su, f"{su}・{'良' if going.startswith('良') else '道悪'}",
                 f"{su}・{'〜1400' if dist <= 1400 else '1600-2000' if dist <= 2000 else '2200〜'}", f"{su}・{'牝' if sex.startswith('牝') else '牡セ'}"]
        for a, s in ANC.items():
            if names & s:
                for cd in conds:
                    x = agg[(a, cd)][pr]; x[0] += 1; x[1] += fin <= 3; x[2] += exp[p]; x[3] += fk
    L = ["# 第4章 ネヴァーセイダイ系・ネイティヴダンサー系・レイズアネイティヴ系（p136-149）の検証（自動生成 tools/book_ch4_native.py）", "",
         "- 5代血統表に該当の祖先を持つ馬。A/E＝3着内の実数÷人気から見込む数。発見2021-23 / 確認2024 / テスト2025-26。◎＝3期間とも1.10以上、○＝1.05以上、×＝0.90以下、▽＝0.95以下。", "",
         "| 祖先 | 条件 | 走数 | A/E | 複勝回収 |", "|---|---|---|---|---|"]
    for k in sorted(agg):
        A = agg[k]
        if min(x[0] for x in A) < 40:
            continue
        ae = [x[1] / x[2] for x in A]
        m = "◎" if min(ae) >= 1.1 else "○" if min(ae) >= 1.05 else "×" if max(ae) <= 0.9 else "▽" if max(ae) <= 0.95 else ""
        L.append(f"| {k[0]} | {m}{k[1]} | " + "/".join(str(x[0]) for x in A) + " | " + "/".join(f"{v:.2f}" for v in ae) + " | " + "/".join(f"{x[3]/x[0]:.0f}" for x in A) + "% |")
    (ROOT / "docs" / "analysis" / "book_ch4_native.md").write_text("\n".join(L) + "\n", encoding="utf-8")
    print("\n".join(L))


if __name__ == "__main__":
    main(sys.argv[1])
