"""★血統穴が来る条件（2026-10-25, ユーザー指示）. data/cache/tag_rows.json（tools/tag_backtest.py）を、人気帯・芝ダ・馬場・頭数・クラス・一緒に付いた材料で分ける.
使い方: python3 tools/star_check.py → docs/analysis/star_check.md"""
import json, re, sqlite3
from collections import defaultdict
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]


def main():
    rows = [r for r in json.load(open(ROOT / "data" / "cache" / "tag_rows.json")) if r["fin"] and r["pop"]]
    c = sqlite3.connect(ROOT / "data" / "keiba.db")
    info = {r[0]: r[1:] for r in c.execute("select race_id,surface,going,grade,course,distance from races")}
    b3, b5 = defaultdict(lambda: [0, 0]), defaultdict(lambda: [0, 0])
    for r in rows:
        p = min(r["pop"], 16); b3[p][0] += 1; b3[p][1] += r["fin"] <= 3; b5[p][0] += 1; b5[p][1] += r["fin"] <= 5
    e3 = {k: v[1] / v[0] for k, v in b3.items()}; e5 = {k: v[1] / v[0] for k, v in b5.items()}
    agg = defaultdict(lambda: [0, 0, 0.0, 0, 0.0, 0, 0, [0, 0]])
    for r in rows:
        tags = {re.sub(r"[◎○×▽▼]+$", "", t) for t in r["tags"]}
        if "★血統穴" not in tags:
            continue
        su, g, gr, co, dist = info.get(r["rid"], (None,) * 5)
        p = r["pop"]
        plus = sum(1 for t in r["tags"] if t.endswith(("○", "◎")))
        minus = sum(1 for t in r["tags"] if t.endswith(("×", "▽", "▼")))
        keys = ["全体", f"人気 {'8-9' if p <= 9 else '10-12' if p <= 12 else '13-'}", f"{su}", f"{su}・{'良' if (g or '良').startswith('良') else '道悪'}",
                f"クラス {gr or '平場/特別'}", f"頭数 {'〜12' if r['n'] <= 12 else '13〜15' if r['n'] <= 15 else '16〜'}",
                f"○◎の数 {min(plus, 3)}", f"×▽▼の数 {min(minus, 2)}", f"○−× {max(min(plus - minus, 3), -2)}",
                f"単勝 {'〜19.9' if (r['odds'] or 0) < 20 else '20〜49.9' if r['odds'] < 50 else '50〜'}倍"]
        keys += [f"＋{t}" for t in tags if t != "★血統穴"]
        half = 0 if r["date"] < "2026-04-01" else 1
        for k in keys:
            a = agg[k]; q = min(p, 16)
            a[0] += 1; a[1] += r["fin"] <= 3; a[2] += e3[q]; a[3] += r["fin"] <= 5; a[4] += e5[q]; a[5] += r["tan"]; a[6] += r["fuku"]; a[7][half] += 1 if r["fin"] <= 3 else 0
    L = ["# ★血統穴が来る条件（過去1年・本番と同じ予想を作り直し, tools/star_check.py）", "",
         "| 条件 | 頭数 | 3着内率 | 3着内A/E | 5着内A/E | 単勝回収 | 複勝回収 | 3着内（前半/後半） |", "|---|---|---|---|---|---|---|---|"]
    for k in sorted(agg, key=lambda k: (not k == "全体", k.startswith("＋"), -agg[k][0])):
        a = agg[k]
        if a[0] < 40:
            continue
        L.append(f"| {k} | {a[0]} | {a[1] / a[0]:.1%} | {a[1] / a[2]:.2f} | {a[3] / a[4]:.2f} | {a[5] / a[0]:.0f}% | {a[6] / a[0]:.0f}% | {a[7][0]}/{a[7][1]} |")
    (ROOT / "docs" / "analysis" / "star_check.md").write_text("\n".join(L) + "\n", encoding="utf-8")
    print("\n".join(L))


if __name__ == "__main__":
    main()
