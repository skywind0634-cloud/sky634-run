"""大井・高知の最終レース（ファイナルレース）の分析（data/nar/<コード>.jsonl, keiba/nar.py が取得）.

- 期間を前半・後半に分け、前半で見つけた傾向が後半でも続くかを確かめる（偶然の排除）。
- 単勝・複勝は実際の払戻。人気は確定人気。
出力: docs/analysis/nar_final.md
"""
from __future__ import annotations

import json
import re
import statistics as stt
import sys
from collections import defaultdict
from itertools import combinations, permutations
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
FILES = {"大井": ROOT / "data/nar/20.jsonl", "高知": ROOT / "data/nar/31.jsonl"}
SPLIT = "2025-04-01"


def load(fn):
    rs = []
    for line in fn.read_text(encoding="utf-8").splitlines():
        try:
            r = json.loads(line)
        except ValueError:
            continue
        r["entries"] = [e for e in r["entries"] if e.get("fin") and e.get("pop")]
        if len(r["entries"]) >= 5:
            r["half"] = "前半" if r["date"] < SPLIT else "後半"
            rs.append(r)
    return rs


def pay(r, kind, combo):
    keys = {"単勝": ["単勝"], "複勝": ["複勝"], "馬連": ["馬連複"], "馬単": ["馬連単"], "ワイド": ["ワイド"], "三連複": ["三連複"], "三連単": ["三連単"]}[kind]
    want = "-".join(map(str, combo))
    want_s = "-".join(map(str, sorted(combo)))
    out = 0
    for k in keys:
        for c, y, _ in r["pay"].get(k, []):
            c2 = "-".join(str(int(x)) for x in re.findall(r"\d+", c))
            if kind in ("馬単", "三連単"):
                if c2 == want:
                    out += y
            elif "-".join(sorted(c2.split("-"), key=int)) == want_s:
                out += y
    return out


def pctl(v, q):
    v = sorted(v)
    return v[min(len(v) - 1, int(q * len(v)))] if v else 0


# ---------------------------------------------------------------- 特徴（レース前に分かるもの）
def prev(e, i=0):
    p = e.get("past") or []
    return p[i] if len(p) > i else None


def style(passing):
    if not passing:
        return None
    try:
        first = int(re.split(r"[-]", passing)[0])
    except ValueError:
        return None
    return "逃げ・先行" if first <= 3 else "中団" if first <= 7 else "後方"


def feats(e, r):
    p1 = prev(e)
    f = {
        "人気": f"{e['pop']}番人気" if e["pop"] <= 9 else "10番人気↓",
        "枠": "内(1-2枠)" if (e.get("gate") or 0) <= 2 else "外(7-8枠)" if (e.get("gate") or 0) >= 7 else "中(3-6枠)",
        "騎手": e.get("jockey"),
        "調教師": e.get("trainer"),
        "父": e.get("sire"),
        "母父": e.get("damsire"),
        "性齢": f"{e.get('sex')}{min(e.get('age') or 0, 7)}{'↑' if (e.get('age') or 0) >= 7 else ''}",
        "馬体重増減": None if e.get("bwd") is None else "-8kg以下" if e["bwd"] <= -8 else "+8kg以上" if e["bwd"] >= 8 else "±6以内",
        "距離": f"{r['distance']}m",
        "頭数": "〜9頭" if r["n_runners"] <= 9 else "10-11頭" if r["n_runners"] <= 11 else "12頭〜",
        "馬場": r.get("going"),
        "季節": {12: "冬", 1: "冬", 2: "冬", 3: "春", 4: "春", 5: "春", 6: "夏", 7: "夏", 8: "夏"}.get(int(r["date"][5:7]), "秋"),
    }
    if p1:
        f["前走着順"] = "前走1-3着" if (p1.get("fin") or 99) <= 3 else "前走4-6着" if (p1.get("fin") or 99) <= 6 else "前走7着↓"
        if p1.get("pop") and p1.get("fin"):
            d = p1["pop"] - p1["fin"]
            f["前走 人気と着順"] = "人気より3着以上上" if d >= 3 else "人気より3着以上下" if d <= -3 else "人気なり"
        f["前走人気"] = "前走1-3人気" if (p1.get("pop") or 99) <= 3 else "前走4-6人気" if (p1.get("pop") or 99) <= 6 else "前走7人気↓"
        f["前走脚質"] = style(p1.get("passing"))
        f["距離変化"] = "同距離" if p1.get("dist") == r["distance"] else "延長" if (p1.get("dist") or 0) < r["distance"] else "短縮"
        f["前走ファイナル"] = "前走もファイナル" if "ファイナル" in (p1.get("class") or "") else "前走は別のレース"
        f["前走他場"] = "前走他場" if p1.get("course") and p1["course"].rstrip("ナ") != r.get("baba") else "前走同場"  # 「大井ナ」はナイター
        if p1.get("last3f") and p1.get("heads"):
            pass
        try:
            import datetime as dt
            days = (dt.date.fromisoformat(r["date"]) - dt.date.fromisoformat(p1["date"])).days
            f["間隔"] = "連闘・中1週" if days <= 14 else "中2-4週" if days <= 35 else "中5-9週" if days <= 70 else "休み明け"
        except (ValueError, KeyError, TypeError):
            pass
        p2 = prev(e, 1)
        if p2 and p2.get("fin") and p1.get("fin"):
            f["近2走"] = "2走とも3着内" if p1["fin"] <= 3 and p2["fin"] <= 3 else "2走とも6着↓" if p1["fin"] >= 6 and p2["fin"] >= 6 else "まちまち"
    else:
        f["前走着順"] = "初出走/転入初戦"
    return f


class Acc:
    def __init__(self):
        self.n = self.w = self.t3 = self.wp = self.pp = 0

    def add(self, e, r):
        self.n += 1
        self.w += e["fin"] == 1
        self.t3 += e["fin"] <= 3
        self.wp += pay(r, "単勝", (e["num"],))
        self.pp += pay(r, "複勝", (e["num"],))


def section_overview(name, rs, L):
    L += [f"## {name}: 概要（{len(rs)}レース, {rs[0]['date']}〜{rs[-1]['date']}）", ""]
    n = [r["n_runners"] for r in rs]
    dist = defaultdict(int)
    for r in rs:
        dist[r["distance"]] += 1
    L.append(f"- 頭数: 平均{stt.mean(n):.1f}頭（最少{min(n)}・最多{max(n)}）。距離: " + "、".join(f"{d}m {c}回" for d, c in sorted(dist.items(), key=lambda x: -x[1])[:5]))
    names = defaultdict(int)
    for r in rs:
        k = re.sub(r"[０-９\d]+.*$", "", r["name"].split()[-1])[:20]
        names[k] += 1
    L.append("- レース名（多い順）: " + "、".join(f"{k}({v})" for k, v in sorted(names.items(), key=lambda x: -x[1])[:6]))
    L += ["", "| 券種 | 中央値 | 上位25% | 上位10% | 最高 | 1万円以上の割合 |", "|---|--:|--:|--:|--:|--:|"]
    for k, kk in (("単勝", "単勝"), ("馬連", "馬連複"), ("馬単", "馬連単"), ("三連複", "三連複"), ("三連単", "三連単")):
        v = [max([y for _, y, _ in r["pay"].get(kk, [])] or [0]) for r in rs if r["pay"].get(kk)]
        if v:
            L.append(f"| {k} | {stt.median(v):,.0f}円 | {pctl(v, .75):,.0f}円 | {pctl(v, .9):,.0f}円 | {max(v):,.0f}円 | {sum(x >= 10000 for x in v) / len(v):.0%} |")
    # 勝ち馬・3着内の人気
    win_pop = defaultdict(int)
    for r in rs:
        for e in r["entries"]:
            if e["fin"] == 1:
                win_pop[min(e["pop"], 10)] += 1
    L += ["", "- 勝ち馬の人気: " + "、".join(f"{k if k < 10 else '10↓'}番人気 {v / len(rs):.0%}" for k, v in sorted(win_pop.items())), ""]


def section_pop(name, rs, L):
    L += [f"### {name}: 人気別（単勝・複勝の回収率, 前半/後半）", "", "| 人気 | 頭数 | 勝率 | 3着内率 | 単回収 前半/後半 | 複回収 前半/後半 |", "|---|--:|--:|--:|--:|--:|"]
    acc = defaultdict(lambda: {"前半": Acc(), "後半": Acc()})
    for r in rs:
        for e in r["entries"]:
            acc[min(e["pop"], 10)][r["half"]].add(e, r)
    for p in sorted(acc):
        a, b = acc[p]["前半"], acc[p]["後半"]
        n = a.n + b.n
        L.append(f"| {p if p < 10 else '10↓'} | {n} | {(a.w + b.w) / n:.1%} | {(a.t3 + b.t3) / n:.1%} | "
                 f"{a.wp / max(a.n, 1):.0f}% / {b.wp / max(b.n, 1):.0f}% | {a.pp / max(a.n, 1):.0f}% / {b.pp / max(b.n, 1):.0f}% |")
    L.append("")


def section_feats(name, rs, L, min_n=40):
    """人気帯ごとに特徴の単複回収率。前半で100%超（単 or 複）・min_n頭以上 → 後半でも100%超のものを残す。"""
    L += [f"### {name}: 前半・後半とも回収率100%超の特徴（人気帯別）", ""]
    bands = {"1-3人気": (1, 3), "4-6人気": (4, 6), "7人気↓": (7, 99)}
    rows = []
    tested = 0
    for bname, (lo, hi) in bands.items():
        acc = defaultdict(lambda: {"前半": Acc(), "後半": Acc()})
        for r in rs:
            for e in r["entries"]:
                if not (lo <= e["pop"] <= hi):
                    continue
                for k, v in feats(e, r).items():
                    if k == "人気" or v is None:
                        continue
                    acc[(k, v)][r["half"]].add(e, r)
        for (k, v), d in acc.items():
            a, b = d["前半"], d["後半"]
            if a.n < min_n or b.n < min_n * 0.6:
                continue
            for kind, fa, fb in (("単", a.wp / a.n, b.wp / b.n), ("複", a.pp / a.n, b.pp / b.n)):
                tested += 1
                if fa >= 100 and fb >= 100:
                    rows.append((bname, k, v, kind, a.n, b.n, fa, fb, (a.t3 + b.t3) / (a.n + b.n)))
    L.append(f"- 調べた組み合わせ {tested}。偶然でも数%は100%超が両期間に出るので、頭数が多く両期間とも大きく超えるものほど信頼できる。")
    if rows:
        L += ["", "| 人気帯 | 特徴 | 券種 | 頭数 前半/後半 | 回収率 前半/後半 | 3着内率 |", "|---|---|---|--:|--:|--:|"]
        for bname, k, v, kind, na, nb, fa, fb, t3 in sorted(rows, key=lambda x: -(x[4] + x[5]))[:40]:
            L.append(f"| {bname} | {k}＝{v} | {kind} | {na}/{nb} | {fa:.0f}% / {fb:.0f}% | {t3:.0%} |")
    L.append("")
    return rows


def section_strategies(name, rs, L, rows):
    """簡単な買い方の回収率（前半/後半）."""
    def by_pop(r):
        return {e["pop"]: e["num"] for e in r["entries"]}

    def strat_tickets(r, s):
        P = by_pop(r)
        sel = lambda a, b: [P[i] for i in range(a, b + 1) if i in P]   # noqa: E731
        if s == "馬連 1人気-2〜6人気":
            return [("馬連", (P[1], x)) for x in sel(2, 6)] if 1 in P else []
        if s == "馬連 BOX 1〜4人気":
            return [("馬連", c) for c in combinations(sel(1, 4), 2)]
        if s == "馬連 2人気-3〜7人気":
            return [("馬連", (P[2], x)) for x in sel(3, 7)] if 2 in P else []
        if s == "三連複 1人気-2〜6人気":
            return [("三連複", (P[1], *c)) for c in combinations(sel(2, 6), 2)] if 1 in P else []
        if s == "三連単 1人気1着固定-2〜5人気-2〜5人気":
            return [("三連単", (P[1], a, b)) for a, b in permutations(sel(2, 5), 2)] if 1 in P else []
        if s == "三連単 2〜3人気1着-1〜5人気-1〜5人気":
            out = []
            for f in sel(2, 3):
                for a, b in permutations([x for x in sel(1, 5) if x != f], 2):
                    out.append(("三連単", (f, a, b)))
            return out
        if s == "三連単 1〜3人気→1〜3人気→4〜8人気":
            return [("三連単", (a, b, c)) for a, b in permutations(sel(1, 3), 2) for c in sel(4, 8)]
        if s == "ワイド 1人気-4〜7人気":
            return [("ワイド", (P[1], x)) for x in sel(4, 7)] if 1 in P else []
        return []

    S = ["馬連 1人気-2〜6人気", "馬連 BOX 1〜4人気", "馬連 2人気-3〜7人気", "ワイド 1人気-4〜7人気", "三連複 1人気-2〜6人気",
         "三連単 1人気1着固定-2〜5人気-2〜5人気", "三連単 2〜3人気1着-1〜5人気-1〜5人気", "三連単 1〜3人気→1〜3人気→4〜8人気"]
    L += [f"### {name}: 人気順で組む買い方の回収率", "", "| 買い方 | 点数 | 前半 | 後半 | 的中率 |", "|---|--:|--:|--:|--:|"]
    for s in S:
        res = {}
        hit = n = 0
        pts = 0
        for half in ("前半", "後半"):
            cost = back = 0
            for r in rs:
                if r["half"] != half:
                    continue
                T = strat_tickets(r, s)
                if not T:
                    continue
                pts = len(T)
                c = 100 * len(T)
                b = sum(pay(r, k, h) for k, h in T)
                cost += c
                back += b
                n += 1
                hit += b > 0
            res[half] = back / cost if cost else 0
        L.append(f"| {s} | {pts} | {res['前半']:.0%} | {res['後半']:.0%} | {hit / max(n, 1):.0%} |")
    L.append("")


def main():
    L = ["# 大井・高知 最終レース（ファイナルレース）の分析（自動生成, tools/nar_final_analysis.py）", "",
         f"- データ: keiba.go.jp の成績表・出馬表（`keiba/nar.py`）。前半＝{SPLIT}より前、後半＝それ以降。",
         "- 単勝・複勝・馬連・三連単などはすべて実際の払戻。人気は確定人気（前売りとはずれる）。", ""]
    for name, fn in FILES.items():
        if not fn.exists():
            L.append(f"## {name}: データなし\n")
            continue
        rs = sorted(load(fn), key=lambda r: r["date"])
        if not rs:
            continue
        section_overview(name, rs, L)
        section_pop(name, rs, L)
        rows = section_feats(name, rs, L)
        section_strategies(name, rs, L, rows)
    out = ROOT / "docs" / "analysis" / "nar_final.md"
    out.write_text("\n".join(L) + "\n", encoding="utf-8")
    print(out)


if __name__ == "__main__":
    main()
