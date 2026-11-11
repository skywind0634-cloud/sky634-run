"""フラグ馬からの買い方の総当たり（2026-11-08 ユーザー「分析やり直せ。後から分かりましたはもう通用しない」）.
11/8 アルゼンチン共和国杯（+5以上の人気薄6頭のうち3頭で 3連複1,635,170円・3連単12,065,300円）を事前に取れなかった反省で、
レース前に分かる情報（フラグ点・単勝オッズ・人気・距離・頭数・クラス）だけで組める買い方を総当たりし、
期間ごとの回収・的中と「高配当（3連複10万円以上・3連単100万円以上）をいくつ事前に拾えたか」を出す.
データ: data/cache/flag_backtest_rows_items.json（5年分・馬ごとの材料）＋ DB の単勝オッズ・払戻。フラグ点は flag_weights.json の excluded を数えない.
使い方: python3 tools/flag_ticket_search.py → docs/analysis/flag_ticket_search.md"""
import itertools, json, sqlite3
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
GOOD, BAD = ("○", "◎"), ("×", "▽", "▼")
ROOTD = (1200, 1600, 2000, 2400)
PER = ("2021-23", "2024", "2025-26/9", "実戦10月〜")


def period(d):
    return "2021-23" if d < "2024" else "2024" if d < "2025" else "2025-26/9" if d < "2026-10" else "実戦10月〜"


def load():
    ex = set(json.load(open(ROOT / "data" / "knowledge" / "flag_weights.json")).get("excluded", []))
    rows = json.load(open(ROOT / "data" / "cache" / ("flag_backtest_rows" + __import__("os").environ.get("ROWS_SFX", "_items") + ".json")))
    c = sqlite3.connect(ROOT / "data" / "keiba.db")
    by = defaultdict(list)
    for r in rows:
        sc = sum((1 if mk in GOOD else -1 if mk in BAD else 0) for name, mk in (r.get("flags") or []) if f"{name}|{mk}" not in ex)
        by[r["rid"]].append((r["pop"], r["fin"], sc, r["date"]))
    out = []
    for rid, hs in by.items():
        res = {p: (num, odds) for num, p, odds in c.execute("select number,popularity,odds from results where race_id=?", (rid,)) if p}
        info = c.execute("select payouts,grade,distance,surface from races where race_id=?", (rid,)).fetchone()
        if not res or not info or not info[0]:
            continue
        pj = json.loads(info[0])
        horses = [dict(num=res[p][0], pop=p, odds=res[p][1] or 0, fin=fin, sc=sc) for p, fin, sc, d in hs if p in res and fin]
        if len(horses) < 5:
            continue
        P = {k: {a: y for a, y in pj.get(k, [])} for k in ("単勝", "ワイド", "3連複", "3連単", "馬連")}
        out.append(dict(rid=rid, date=hs[0][3], grade=info[1], dist=info[2] or 0, surf=info[3], n=len(horses), horses=horses, pay=P))
    return out


def K(nums):
    return "-".join(map(str, sorted(nums)))


def tickets(r, kind, grp, pop_top=None):
    """grp: 選ばれた馬の馬番リスト（フラグ点順）. 戻り値: [(券種, 組)]"""
    if kind == "単勝":
        return [("単勝", str(n)) for n in grp]
    if kind == "ワイドBOX":
        return [("ワイド", K(p)) for p in itertools.combinations(grp, 2)]
    if kind == "3連複BOX":
        return [("3連複", K(p)) for p in itertools.combinations(grp, 3)]
    if kind == "3連単BOX":
        return [("3連単", "-".join(map(str, p))) for p in itertools.permutations(grp, 3)]
    if kind == "3連複 2頭×1〜3人気":
        return list({("3連複", K((a, b, t))) for a, b in itertools.combinations(grp, 2) for t in pop_top if t not in (a, b)})
    if kind == "ワイド×1〜3人気":
        return list({("ワイド", K((a, t))) for a in grp for t in pop_top if t != a})
    raise ValueError(kind)


KINDS = ("単勝", "ワイドBOX", "3連複BOX", "3連単BOX", "3連複 2頭×1〜3人気", "ワイド×1〜3人気")
SEG = {"全距離": lambda r: True, "非根幹": lambda r: r["dist"] not in ROOTD, "根幹": lambda r: r["dist"] in ROOTD,
       "重賞": lambda r: r["grade"] in ("G1", "G2", "G3"), "16頭以上": lambda r: r["n"] >= 16}


def evaluate(races, T, X, mink, cap, kind, seg):
    agg = defaultdict(lambda: [0, 0, 0, 0, 0])  # races, bet, ret, hit_races, big_caught
    big_total = defaultdict(int)
    for r in races:
        if not SEG[seg](r):
            continue
        p3 = r["pay"]["3連複"]; t3 = r["pay"]["3連単"]
        big = (max(p3.values(), default=0) >= 100000) or (max(t3.values(), default=0) >= 1000000)
        if big:
            big_total[period(r["date"])] += 1; big_total["全体"] += 1
        cand = sorted((h for h in r["horses"] if h["sc"] >= T and h["odds"] >= X), key=lambda h: (-h["sc"], h["odds"]))
        if len(cand) < mink:
            continue
        grp = [h["num"] for h in cand[:cap]]
        pop_top = [h["num"] for h in sorted(r["horses"], key=lambda h: h["pop"])[:3]]
        if kind in ("3連複BOX", "3連単BOX") and len(grp) < 3:
            continue
        if kind == "ワイドBOX" and len(grp) < 2:
            continue
        tk = tickets(r, kind, grp, pop_top)
        if not tk:
            continue
        ret = sum(r["pay"][{"単勝": "単勝", "ワイド": "ワイド", "3連複": "3連複", "3連単": "3連単"}[a]].get(b, 0) for a, b in tk)
        bigc = big and ret >= 50000
        for k in (period(r["date"]), "全体"):
            a = agg[k]
            a[0] += 1; a[1] += 100 * len(tk); a[2] += ret; a[3] += ret > 0; a[4] += bigc
    return agg, big_total


def main():
    races = load()
    years = 5.83
    res = []
    for seg in SEG:
        for T in (3, 4, 5, 6):
            for X in (10, 20):
                for mink in (1, 2, 3):
                    for cap in (3, 4, 5, 6):
                        for kind in KINDS:
                            if kind == "単勝" and (mink > 1 or cap != 6):
                                continue
                            if kind in ("3連複BOX", "3連単BOX") and mink < 3:
                                continue
                            if kind == "3連単BOX" and cap > 6:
                                continue
                            agg, bt = evaluate(races, T, X, mink, cap, kind, seg)
                            if "全体" not in agg or agg["全体"][0] < 15:
                                continue
                            rr = {k: (agg[k][2] / agg[k][1] if k in agg and agg[k][1] else None) for k in PER + ("全体",)}
                            res.append(dict(seg=seg, T=T, X=X, mink=mink, cap=cap, kind=kind, rr=rr, agg=agg, bt=bt))
    def stable(x):
        v = [x["rr"][k] for k in PER[:3]]
        return all(y is not None and y >= 1.0 for y in v)
    L = ["# フラグ馬からの買い方の総当たり（tools/flag_ticket_search.py, 2026-11-08）", "",
         "レース前に分かる情報だけで組める買い方を総当たり。T＝フラグ点の下限、X＝単勝の下限（倍）、K＝その馬が何頭以上いるレース、上位＝フラグ点の上位何頭まで。",
         "高配当＝3連複10万円以上または3連単100万円以上のレース。「拾えた高配当」はそのレースで5万円以上の払戻があったもの。1点100円。", "",
         "## 3期（2021-23 / 2024 / 2025-26/9）すべてで回収100%以上の買い方", "",
         "| 区分 | 買い方 | T | X | K | 上位 | 2021-23 | 2024 | 2025-26/9 | 実戦10月〜 | 全体 | レース数 | 年あたり投資 | 的中レース率 | 拾えた高配当 |", "|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|"]
    def row(x):
        a = x["agg"]["全体"]
        f = lambda v: "-" if v is None else f"{v:.0%}"
        return (f"| {x['seg']} | {x['kind']} | +{x['T']} | {x['X']}倍 | {x['mink']} | {x['cap']} | " + " | ".join(f(x["rr"][k]) for k in PER)
                + f" | {f(x['rr']['全体'])} | {a[0]} | {a[1] / years:,.0f}円 | {a[3] / a[0]:.0%} | {a[4]}/{x['bt'].get('全体', 0)} |")
    st = sorted([x for x in res if stable(x)], key=lambda x: (-min(x["rr"][k] for k in PER[:3]), -x["agg"]["全体"][0]))
    L += [row(x) for x in st[:60]] or ["| （なし） |"]
    L += ["", "## 高配当を一番多く事前に拾えた買い方（全体の回収80%以上）", "",
          "| 区分 | 買い方 | T | X | K | 上位 | 2021-23 | 2024 | 2025-26/9 | 実戦10月〜 | 全体 | レース数 | 年あたり投資 | 的中レース率 | 拾えた高配当 |", "|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|"]
    bg = sorted([x for x in res if (x["rr"]["全体"] or 0) >= 0.8], key=lambda x: (-x["agg"]["全体"][4], -(x["rr"]["全体"] or 0)))
    L += [row(x) for x in bg[:40]]
    (ROOT / "docs" / "analysis" / "flag_ticket_search.md").write_text("\n".join(L) + "\n", encoding="utf-8")
    # 高配当レースの中身: 1〜3着にフラグ+5以上が何頭いたか
    dist = defaultdict(lambda: defaultdict(int))
    for r in races:
        p3 = r["pay"]["3連複"]; t3 = r["pay"]["3連単"]
        if (max(p3.values(), default=0) >= 100000) or (max(t3.values(), default=0) >= 1000000):
            top = [h for h in r["horses"] if h["fin"] <= 3]
            dist[period(r["date"])][sum(h["sc"] >= 5 for h in top)] += 1
            dist["全体"][sum(h["sc"] >= 4 for h in top) + 10] += 1
    print("\n".join(L[:8 + min(len(st), 60)]))
    print("\n高配当レースの1〜3着にフラグ+5以上が何頭いたか:", {k: dict(v) for k, v in dist.items()})


if __name__ == "__main__":
    main()
