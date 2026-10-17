"""上位人気のオッズの形（1番人気の倍率・上位の拮抗＝混戦度）ごとの検証（2026-10-17 ユーザー指摘）.
全馬の単勝オッズ（backfill-odds で補完）が入ったレースだけを使う。対象＝7R以降・未勝利/新馬/障害を除く。
(1) 1〜3番人気を倍率の帯で分け、勝率・3着内率・単勝/複勝回収率を出す
(2) レースの形（1番人気の倍率 × 2番人気との比）ごとに、7番人気以下が3着内に来た率・1〜3番人気が全滅した率・3連複の中央払戻を出す
(3) 形ごとに買い方（人気馬中心と穴絡み）の回収率を出す
期間は 2021-23 / 2024 / 2025-26。
使い方: python3 tools/odds_structure.py [DBのパス] → docs/analysis/odds_structure.md
"""
import itertools, json, sqlite3, statistics, sys
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def per(d):
    return 0 if d < "2024-01-01" else 1 if d < "2025-01-01" else 2


def norm(c):
    return "-".join(sorted([str(x) for x in c if str(x).isdigit()], key=int))


def band(o):
    for th, lab in ((1.5, "〜1.5"), (2.0, "1.6〜2.0"), (2.5, "2.1〜2.5"), (3.0, "2.6〜3.0"), (4.0, "3.1〜4.0"), (5.5, "4.1〜5.5"), (8.0, "5.6〜8.0")):
        if o <= th:
            return lab
    return "8.1〜"


def shape(o1, o2):
    """レースの形: 1番人気の倍率と、2番人気÷1番人気（1.3未満＝拮抗）."""
    b = "1人気2.0以下" if o1 <= 2.0 else "1人気2.1〜3.0" if o1 <= 3.0 else "1人気3.1〜4.0" if o1 <= 4.0 else "1人気4.1以上"
    return b + ("・2人気と拮抗" if o2 / o1 < 1.3 else "・抜けた1番人気" if o2 / o1 >= 2.0 else "")


def load(db):
    c = sqlite3.connect(db)
    races = {}
    for rid, date, rno, grade, surf, name, pay in c.execute(
            "select race_id,date,race_no,grade,surface,name,payouts from races where date>='2021-01-01'"):
        if (rno or 0) < 7 or grade in ("未勝利", "新馬") or surf not in ("芝", "ダ"):
            continue
        races[rid] = dict(date=date, pay=json.loads(pay) if pay else {}, hs=[])
    for rid, num, pop, odds, fin in c.execute("select race_id,number,popularity,odds,finish from results"):
        if rid in races and fin:
            races[rid]["hs"].append(dict(num=num, pop=pop, odds=odds, fin=fin))
    out = []
    for rid, R in races.items():
        hs = [h for h in R["hs"] if h["pop"]]
        if len(hs) < 8 or sum(1 for h in hs if h["odds"]) < len(hs) - 1:
            continue
        hs.sort(key=lambda h: h["pop"])
        if not (hs[0]["odds"] and hs[1]["odds"]):
            continue
        R["hs"] = hs
        R["P"] = {k: {norm(str(a).replace("－", "-").split("-")): y for a, y in v} for k, v in R["pay"].items()}
        R["rid"] = rid
        out.append(R)
    return out


def main(db=None):
    races = load(db or ROOT / "data" / "keiba.db")
    L = ["# 上位人気のオッズの形ごとの検証（自動生成 tools/odds_structure.py）", "",
         f"- 全馬のオッズがあるレース {len(races)} 件。期間＝2021-23 / 2024 / 2025-26。1点100円。", ""]

    # (1) 人気×倍率帯
    a1 = defaultdict(lambda: [[0, 0, 0, 0, 0] for _ in range(3)])
    for R in races:
        p = per(R["date"])
        tk = R["P"].get("単勝", {}); fk = R["P"].get("複勝", {})
        for h in R["hs"][:3]:
            if not h["odds"]:
                continue
            a = a1[(h["pop"], band(h["odds"]))][p]
            a[0] += 1; a[1] += h["fin"] == 1; a[2] += h["fin"] <= 3; a[3] += tk.get(str(h["num"]), 0); a[4] += fk.get(str(h["num"]), 0)
    L += ["## 1. 1〜3番人気の倍率の帯ごと", "", "| 人気 | 倍率 | 頭数 | 勝率 | 3着内率 | 単勝回収 | 複勝回収 |", "|---|---|---|---|---|---|---|"]
    for k in sorted(a1, key=lambda k: (k[0], float(k[1].replace("〜", " ").split()[0]) if k[1][0] != "〜" else 0)):
        A = a1[k]
        if sum(x[0] for x in A) < 30:
            continue
        L.append(f"| {k[0]} | {k[1]} | " + "/".join(str(x[0]) for x in A) + " | " + "/".join(f"{x[1] / max(x[0], 1) * 100:.0f}%" for x in A)
                 + " | " + "/".join(f"{x[2] / max(x[0], 1) * 100:.0f}%" for x in A) + " | " + "/".join(f"{x[3] / max(x[0], 1):.0f}" for x in A)
                 + " | " + "/".join(f"{x[4] / max(x[0], 1):.0f}" for x in A) + " |")

    # (2) レースの形
    a2 = defaultdict(lambda: [[0, 0, 0, []] for _ in range(3)])
    for R in races:
        p = per(R["date"]); hs = R["hs"]
        s = shape(hs[0]["odds"], hs[1]["odds"])
        top3 = [h for h in hs if h["fin"] <= 3]
        a = a2[s][p]; a[0] += 1
        a[1] += any(h["pop"] >= 7 for h in top3)
        a[2] += not any(h["pop"] <= 3 for h in top3)
        t = list(R["P"].get("3連複", {}).values())
        if t:
            a[3].append(t[0])
    L += ["", "## 2. レースの形ごとの荒れ方", "", "| 形 | レース数 | 7番人気以下が3着内 | 1〜3番人気が全滅 | 3連複の中央払戻 |", "|---|---|---|---|---|"]
    for s in sorted(a2):
        A = a2[s]
        L.append(f"| {s} | " + "/".join(str(x[0]) for x in A) + " | " + "/".join(f"{x[1] / max(x[0], 1) * 100:.0f}%" for x in A) + " | "
                 + "/".join(f"{x[2] / max(x[0], 1) * 100:.0f}%" for x in A) + " | " + "/".join(f"{statistics.median(x[3]) if x[3] else 0:,.0f}" for x in A) + " |")

    # (3) 形ごとの買い方
    def bets(hs, kind):
        pop = {h["pop"]: h["num"] for h in hs}
        g = lambda *ps: [pop[x] for x in ps if x in pop]  # noqa: E731
        if any(x not in pop for x in (1, 2, 3)):
            return set()   # 人気の同順（同オッズ）で1〜3番人気が欠けるレースは除く
        if kind == "3連複 1人気軸-2〜5人気BOX(6点)":
            return {("3連複", norm([pop[1], x, y])) for x, y in itertools.combinations(g(2, 3, 4, 5), 2)}
        if kind == "3連複 1〜3人気-1〜3人気-4〜8人気(15点)":
            return {("3連複", norm([pop[x], pop[y], z])) for x, y in itertools.combinations((1, 2, 3), 2) for z in g(4, 5, 6, 7, 8)}
        if kind == "3連複 1人気-2〜3人気-6〜12人気(14点)":
            return {("3連複", norm([pop[1], pop[x], z])) for x in (2, 3) for z in g(6, 7, 8, 9, 10, 11, 12)}
        if kind == "ワイド 1人気-2〜4人気(3点)":
            return {("ワイド", norm([pop[1], x])) for x in g(2, 3, 4)}
        if kind == "ワイド 2-3人気(1点)":
            return {("ワイド", norm(g(2, 3)))}
        if kind == "馬連 1人気-2〜4人気(3点)":
            return {("馬連", norm([pop[1], x])) for x in g(2, 3, 4)}
        if kind == "3連複 4〜7人気BOX(4点)":
            return {("3連複", norm(c)) for c in itertools.combinations(g(4, 5, 6, 7), 3)}
        if kind == "ワイド 4〜6人気BOX(3点)":
            return {("ワイド", norm(c)) for c in itertools.combinations(g(4, 5, 6), 2)}
        if kind == "複勝 1人気":
            return {("複勝", norm([pop[1]]))}
        if kind == "単勝 1人気":
            return {("単勝", norm([pop[1]]))}
        return set()

    kinds = ["単勝 1人気", "複勝 1人気", "ワイド 1人気-2〜4人気(3点)", "ワイド 2-3人気(1点)", "馬連 1人気-2〜4人気(3点)",
             "3連複 1人気軸-2〜5人気BOX(6点)", "3連複 1〜3人気-1〜3人気-4〜8人気(15点)", "3連複 1人気-2〜3人気-6〜12人気(14点)",
             "ワイド 4〜6人気BOX(3点)", "3連複 4〜7人気BOX(4点)"]
    a3 = defaultdict(lambda: [[0, 0, 0, 0] for _ in range(3)])
    for R in races:
        p = per(R["date"]); hs = R["hs"]
        s = shape(hs[0]["odds"], hs[1]["odds"])
        for k in kinds:
            bs = bets(hs, k)
            if not bs:
                continue
            ret = sum(R["P"].get(t, {}).get(cmb, 0) for t, cmb in bs)
            for key in ((s, k), ("全レース", k)):
                a = a3[key][p]; a[0] += 1; a[1] += len(bs); a[2] += ret > 0; a[3] += ret
    L += ["", "## 3. 形ごとの買い方（3期間すべて100%超は太字）", "", "| 形 | 買い方 | レース数 | 的中率 | 回収率 |", "|---|---|---|---|---|"]
    for key in sorted(a3, key=lambda k: (k[0] != "全レース", k[0], kinds.index(k[1]))):
        A = a3[key]
        if sum(x[0] for x in A) < 60:
            continue
        roi = [x[3] / max(x[1] * 100, 1) * 100 for x in A]
        b = "**" if min(roi) > 100 and min(x[0] for x in A) >= 30 else ""
        L.append(f"| {key[0]} | {b}{key[1]}{b} | " + "/".join(str(x[0]) for x in A) + " | " + "/".join(f"{x[2] / max(x[0], 1) * 100:.0f}%" for x in A)
                 + " | " + "/".join(f"{r:.0f}%" for r in roi) + " |")
    (ROOT / "docs" / "analysis" / "odds_structure.md").write_text("\n".join(L) + "\n", encoding="utf-8")
    print("\n".join(L))


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else None)
