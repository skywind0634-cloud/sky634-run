"""フラグの材料を1つずつ確かめ、効くものだけを強さ（重み）付きで使う（2026-11-07, ユーザー指摘
「単純に＋−しているから意味ないのでは。マイナスが本当にマイナスか分からない」）.

入力: data/cache/flag_backtest_rows_items.json（SFX=_items python3 tools/flag_backtest.py で各馬の材料名と印を記録）。
- 材料ごとに、学習期間（2021-2024）・確認期間（2025-01〜2026-09）・実戦（2026-10〜）の 3着内 A/E（人気から見込む数との比）を出す。
- 学習期間で印の向きどおり（○◎は1.03超・×▽▼は0.97未満, 200走以上）で、確認期間でも同じ向き（100走以上）のものだけ残す。
- 重み＝学習期間のA/Eの対数（走数で少し割り引く）。馬の新しい点＝残った材料の重みの合計（＝人気からの上乗せの見込み）。
- 新しい点と、今の単純な＋−の点を、確認期間・実戦で比べる。
使い方: python3 tools/flag_items_check.py → docs/analysis/flag_items_check.md・data/knowledge/flag_weights.json
"""
import json
import math
import sqlite3
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def period(d):
    return "学習" if d < "2025-01-01" else "確認" if d < "2026-10-01" else "実戦"


def main():
    c = sqlite3.connect(ROOT / "data" / "keiba.db")
    base = defaultdict(lambda: [0, 0])
    for p, f in c.execute("select popularity,finish from results where finish>0 and popularity>0 and race_id in (select race_id from races where date<'2025-01-01')"):
        b = base[min(p, 14)]; b[0] += 1; b[1] += f <= 3
    exp = {k: v[1] / v[0] for k, v in base.items()}
    rows = json.load(open(ROOT / "data" / "cache" / "flag_backtest_rows_items.json"))
    st = defaultdict(lambda: {k: [0, 0, 0.0] for k in ("学習", "確認", "実戦")})
    for r in rows:
        e = exp[min(r["pop"], 14)]
        for name, mark in {tuple(x) for x in r.get("flags", [])}:
            a = st[(name, mark)][period(r["date"])]; a[0] += 1; a[1] += r["fin"] <= 3; a[2] += e
    ae = lambda a: a[1] / a[2] if a[2] else None
    old = {}
    wf = ROOT / "data" / "knowledge" / "flag_weights.json"
    if wf.exists():
        try:
            old = json.load(open(wf)).get("weights", {})
        except ValueError:
            old = {}
    kept, table, excluded = {}, [], []
    for (name, mark), d in st.items():
        tr, te, lv = d["学習"], d["確認"], d["実戦"]
        if tr[0] < 200:
            continue
        plus = mark in "◎○"
        a_tr, a_te = ae(tr), ae(te)
        ok_tr = (a_tr > 1.03) if plus else (a_tr < 0.97)
        ok_te = te[0] >= 100 and ((a_te > 1.0) if plus else (a_te < 1.0))
        # 実戦（2026-10〜、毎週増える）で150走以上たまり、向きが逆になったものは外す（毎週の自動更新で効かなくなった材料を落とす）
        a_lv = ae(lv)
        if lv[0] >= 150 and a_lv is not None and ((a_lv < 0.95) if plus else (a_lv > 1.05)):
            ok_te = False
        w = math.log(a_tr) * tr[0] / (tr[0] + 300) if ok_tr and ok_te else 0.0
        if w:
            kept[f"{name}|{mark}"] = round(w, 4)
        else:
            excluded.append(f"{name}|{mark}")
        table.append((name, mark, tr[0], a_tr, te[0], a_te, lv[0], ae(lv), "残す" if w else "外す"))
    import datetime as _dt
    json.dump({"_meta": {"tool": "tools/flag_items_check.py", "updated": _dt.date.today().isoformat(),
                         "note": "重み＝学習期間(2021-24)のA/Eの対数（走数で割り引き）。確認期間(2025-01〜2026-09)でも同じ向きの材料だけ。excluded＝効いていないので点に数えない材料（keiba/digest.py の flag_marks）"},
               "weights": kept, "excluded": sorted(excluded)}, open(wf, "w"), ensure_ascii=False, indent=1)
    newly_out = sorted(k for k in old if k not in kept); newly_in = sorted(k for k in kept if k not in old)
    # 新しい点 vs 今の点
    def score_new(r):
        return sum(kept.get(f"{n}|{m}", 0) for n, m in {tuple(x) for x in r.get("flags", [])})
    L = ["# フラグの材料を1つずつ確かめる（tools/flag_items_check.py）", "",
         "学習＝2021-2024、確認＝2025-01〜2026-09（材料選びに使っていない）、実戦＝2026-10〜11/1。A/E＝3着内の実数÷人気から見込む数。", "",
         f"材料の数: 全{len(table)}（学習期間200走以上）→ 残す {len(kept)}・外す {len(table) - len(kept)}", "",
         "## 今回の更新で変わった材料", "",
         "- 効かなくなって外した: " + ("、".join(newly_out) or "なし"),
         "- 新しく効くと分かって入れた: " + ("、".join(newly_in) or "なし"), "",
         "## 新しい点（重み付き）と今の点（単純な＋−）の比較"]
    for per in ("確認", "実戦"):
        rs = [r for r in rows if period(r["date"]) == per]
        for lab, fn, cuts in (("今の点（＋−の数）", lambda r: r["plus"] - r["minus"], [(5, 99, "+5以上"), (3, 4, "+3〜4"), (1, 2, "+1〜2"), (0, 0, "0"), (-99, -1, "−1以下")]),
                              ("新しい点（重み）", score_new, [(0.30, 99, "0.30以上"), (0.15, 0.2999, "0.15〜0.30"), (0.05, 0.1499, "0.05〜0.15"), (-0.05, 0.0499, "ほぼ0"), (-99, -0.0501, "マイナス")])):
            L += ["", f"### {per}・{lab}", "", "| 点 | 頭数 | 3着内率 | A/E | 単勝回収 | 複勝回収 |", "|---|---|---|---|---|---|"]
            for lo, hi, name in cuts:
                g = [r for r in rs if lo <= fn(r) <= hi]
                if not g:
                    continue
                n = len(g); t3 = sum(r["fin"] <= 3 for r in g); e = sum(exp[min(r["pop"], 14)] for r in g)
                L.append(f"| {name} | {n} | {t3 / n:.0%} | {t3 / e:.2f} | {sum(r['tan'] for r in g) / n:.0f}% | {sum(r['fuku'] for r in g) / n:.0f}% |")
    L += ["", "## 材料ごと（学習期間の走数順・上位80）", "", "| 材料 | 印 | 学習 走数 | 学習 A/E | 確認 走数 | 確認 A/E | 実戦 走数 | 実戦 A/E | 判定 |", "|---|---|---|---|---|---|---|---|---|"]
    for name, mark, n1, a1, n2, a2, n3, a3, v in sorted(table, key=lambda x: -x[2])[:80]:
        f = lambda a: f"{a:.2f}" if a else "-"
        L.append(f"| {name} | {mark} | {n1} | {f(a1)} | {n2} | {f(a2)} | {n3} | {f(a3)} | {v} |")
    (ROOT / "docs" / "analysis" / "flag_items_check.md").write_text("\n".join(L) + "\n", encoding="utf-8")
    print("\n".join(L[:60]))


if __name__ == "__main__":
    main()
