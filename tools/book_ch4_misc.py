"""第4章 その他のノーザンダンサー系・ハンプトン系（p270-277）の検証（2026-10-15）.
- 父サトノクラウン（マルジュ系）: 芝/ダ、良/道悪、芝2000以上
- 欧州型ミスプロ系×ラストタイクーン構成: 5代にLast Tycoon かつ 父or母父がキングマンボ系/マキャヴェリアン系
- 5代にフェアリーキング/エリシオ/ファルブラヴ: 芝1400以下/1600以上、牝/セン
- 5代にディキシーランドバンド: 芝の持続ペース（実際）/その他
- 5代にアサティス: ダ1600以上/1400以下
- 5代にハイペリオン系の名（サッカーボーイ等）: 芝4歳以上の道悪
使い方: python3 tools/book_ch4_misc.py <ped5_full.json> → docs/analysis/book_ch4_misc.md
"""
import json, sqlite3, sys
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
EUMP = {"キングカメハメハ系", "キングマンボ系", "マキャヴェリアン系"}


def per(d):
    return 0 if d < "2024-01-01" else 1 if d < "2025-01-01" else 2


def main(path):
    H = json.loads(Path(path).read_text(encoding="utf-8"))["horses"]
    c = sqlite3.connect(ROOT / "data" / "keiba.db")
    base = defaultdict(lambda: [0, 0]); rows = []
    for date, su, dist, going, pt, hid, fin, pop, num, age, sex, sire, sl, dsl, pay in c.execute(
            """select ra.date, ra.surface, ra.distance, ra.going, ra.pace_type, r.horse_id, r.finish, r.popularity, r.number, r.age, r.sex,
                      h.sire, h.sire_line, h.damsire_line, ra.payouts
               from results r join races ra using(race_id) join horses h using(horse_id)
               where ra.surface in ('芝','ダ') and r.finish is not null and r.popularity is not null"""):
        p = min(pop, 14); b = base[p]; b[0] += 1; b[1] += fin <= 3
        rows.append((date, su, dist or 1600, going or "良", pt, hid, fin, p, num, age, sex or "", sire, sl, dsl, pay))
    exp = {p: v[1] / v[0] for p, v in base.items()}
    agg = defaultdict(lambda: [[0, 0, 0.0, 0] for _ in range(3)]); pc = {}
    for date, su, dist, going, pt, hid, fin, p, num, age, sex, sire, sl, dsl, pay in rows:
        if pay not in pc:
            pc[pay] = {cc: y for cc, y in (json.loads(pay).get("複勝", []) if pay else [])}
        fk = pc[pay].get(str(num), 0)
        nm = set(n for n in (H.get(hid) or []) if n)
        good = "良" if going.startswith("良") else "道悪"
        K = []
        if sire == "サトノクラウン":
            K += [("父サトノクラウン", f"{su}・{good}")] + ([("父サトノクラウン", "芝2000以上")] if su == "芝" and dist >= 2000 else [])
        if nm & {"Last Tycoon", "ラストタイクーン"} and (sl in EUMP or dsl in EUMP):
            K.append(("欧州型ミスプロ系×5代にラストタイクーン", su))
        if nm & {"Fairy King", "フェアリーキング", "エリシオ", "Helissio", "ファルブラヴ", "Falbrav"}:
            K.append(("5代にフェアリーキング系", (f"{su}1400以下" if dist <= 1400 else f"{su}1600以上")))
            K.append(("5代にフェアリーキング系", f"{su}・{'牝' if sex.startswith('牝') else 'セン' if sex.startswith('セ') else '牡'}"))
        if su == "芝" and nm & {"Dixieland Band", "ディキシーランドバンド"}:
            K.append(("5代にディキシーランドバンド", "芝・実際の持続" if pt == "持続" else "芝・その他のペース"))
        if su == "ダ" and nm & {"Assatis", "アサティス"}:
            K.append(("5代にアサティス", "ダ1600以上" if dist >= 1600 else "ダ1400以下"))
        if su == "芝" and (age or 0) >= 4 and nm & {"サッカーボーイ", "Hyperion", "ハイペリオン"}:
            K.append(("5代にサッカーボーイ/ハイペリオン", f"芝4歳以上・{good}"))
        for k in K:
            x = agg[k][per(date)]; x[0] += 1; x[1] += fin <= 3; x[2] += exp[p]; x[3] += fk
    L = ["# 第4章 その他のノーザンダンサー系・ハンプトン系（p270-277）の検証（自動生成 tools/book_ch4_misc.py）", "",
         "- A/E＝3着内の実数÷人気から見込む数。発見2021-23 / 確認2024 / テスト2025-26。◎＝3期間とも1.10以上、○＝1.05以上、×＝0.90以下、▽＝0.95以下。", "",
         "| 血統 | 条件 | 走数 | A/E | 複勝回収 |", "|---|---|---|---|---|"]
    for k in sorted(agg):
        A = agg[k]
        if min(x[0] for x in A) < 30:
            continue
        ae = [x[1] / x[2] for x in A]
        m = "◎" if min(ae) >= 1.1 else "○" if min(ae) >= 1.05 else "×" if max(ae) <= 0.9 else "▽" if max(ae) <= 0.95 else ""
        L.append(f"| {k[0]} | {m}{k[1]} | " + "/".join(str(x[0]) for x in A) + " | " + "/".join(f"{v:.2f}" for v in ae) + " | " + "/".join(f"{x[3]/x[0]:.0f}" for x in A) + "% |")
    (ROOT / "docs" / "analysis" / "book_ch4_misc.md").write_text("\n".join(L) + "\n", encoding="utf-8")
    print("\n".join(L))


if __name__ == "__main__":
    main(sys.argv[1])
