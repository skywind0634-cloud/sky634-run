"""第4章 ヘロド系・マッチェム系（p288-296）の検証（2026-10-15）.
- 5代にメジロマックイーン/パーソロン/シンボリルドルフ: 芝2200以上、芝・道悪
- 5代にインリアリティ: 芝1200以下（「インリアリティの血は日本のスプリント戦に影響」）
- 芝1200以下 × 5代にブラッシンググルーム かつ サンデーサイレンスを持たない（カルストンライトオ/サニングデールの共通点）
- 父マッチェム系（DB上の系統名にマンノウォー/ティズナウ/インリアリティ/ウォーニング等を含む種牡馬）: 芝1200以下
使い方: python3 tools/book_ch4_herod.py <ped5_full.json> → docs/analysis/book_ch4_herod.md
"""
import json, sqlite3, sys
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def per(d):
    return 0 if d < "2024-01-01" else 1 if d < "2025-01-01" else 2


def main(path):
    H = json.loads(Path(path).read_text(encoding="utf-8"))["horses"]
    c = sqlite3.connect(ROOT / "data" / "keiba.db")
    base = defaultdict(lambda: [0, 0]); rows = []
    for date, su, dist, going, hid, fin, pop, num, sire, pay in c.execute(
            """select ra.date, ra.surface, ra.distance, ra.going, r.horse_id, r.finish, r.popularity, r.number, h.sire, ra.payouts
               from results r join races ra using(race_id) join horses h using(horse_id)
               where ra.surface in ('芝','ダ') and r.finish is not null and r.popularity is not null"""):
        p = min(pop, 14); b = base[p]; b[0] += 1; b[1] += fin <= 3
        rows.append((date, su, dist or 1600, going or "良", hid, fin, p, num, sire, pay))
    exp = {p: v[1] / v[0] for p, v in base.items()}
    agg = defaultdict(lambda: [[0, 0, 0.0, 0, 0] for _ in range(3)]); pc = {}
    for date, su, dist, going, hid, fin, p, num, sire, pay in rows:
        if pay not in pc:
            j = json.loads(pay) if pay else {}
            pc[pay] = ({cc: y for cc, y in j.get("複勝", [])}, {cc: y for cc, y in j.get("単勝", [])})
        fk, tk = pc[pay][0].get(str(num), 0), pc[pay][1].get(str(num), 0)
        nm = set(n for n in (H.get(hid) or []) if n)
        if not nm:
            continue
        K = []
        if su == "芝" and nm & {"メジロマックイーン", "パーソロン", "Partholon", "シンボリルドルフ", "メジロティターン"}:
            K.append(("5代にパーソロン系（マックイーン等）", "芝2200以上" if dist >= 2200 else "芝2000以下"))
            K.append(("5代にパーソロン系（マックイーン等）", f"芝・{'良' if going.startswith('良') else '道悪'}"))
        if su == "芝" and dist <= 1200:
            if nm & {"In Reality", "インリアリティ"}:
                K.append(("5代にインリアリティ", "芝1200以下"))
            if nm & {"Blushing Groom", "ブラッシンググルーム"} and not nm & {"Halo", "ヘイロー", "Sunday Silence", "サンデーサイレンス"}:
                K.append(("5代にブラッシンググルーム×サンデーなし", "芝1200以下"))
            if nm & {"Man o' War", "マンノウォー", "Tiznow", "ティズナウ", "Warning", "ウォーニング", "Valid Appeal", "ヴァリッドアピール"}:
                K.append(("5代にマンノウォー系の種牡馬", "芝1200以下"))
        for k in K:
            x = agg[k][per(date)]; x[0] += 1; x[1] += fin <= 3; x[2] += exp[p]; x[3] += fk; x[4] += tk
    L = ["# 第4章 ヘロド系・マッチェム系（p288-296）の検証（自動生成 tools/book_ch4_herod.py）", "",
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
    (ROOT / "docs" / "analysis" / "book_ch4_herod.md").write_text("\n".join(L) + "\n", encoding="utf-8")
    print("\n".join(L))


if __name__ == "__main__":
    main(sys.argv[1])
