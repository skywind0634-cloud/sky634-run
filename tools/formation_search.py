"""3連複フォーメーションの組み方の総当たり（2026-11-08 ユーザー「こういう儲かる買い方を探せ。フォーメーションの組み方とか」）.
1列目×2列目×3列目×レースの絞り込み×買い方 を、JRA の実際の最終オッズ（data/cache/odds）と実際の払戻で採点する.
選ぶ: 2021-23 と 2024（data/cache/flag_backtest_rows_items.json）で両方110%以上・各100レース以上.
確かめる: 2025-01〜26-09 と 実戦（2026-10〜）を、材料を2021-24だけで選んだフラグ（flag_backtest_rows_oos.json）で.
使い方: python3 tools/formation_search.py [並列数] → docs/analysis/formation_search.md"""
import itertools, json, os, sys
from collections import defaultdict
from multiprocessing import Pool
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
ROOTD = (1200, 1600, 2000, 2400)

AXES = [(T, X, two) for T in (4, 5, 6) for X in (1, 5, 10) for two in (False, True)]
C2S = ["人気1-3", "人気1-4", "人気1-5", "フラグ上位3", "テン上位3", "人気1-3+フラグ上位2"]
C3S = ["全頭", "人気1-9", "単勝50倍未満", "フラグ+2以上", "テン上位9"]
FILTERS = {"なし": lambda r: True, "1番人気2.5倍以上": lambda r: r["fav"] >= 2.5, "1番人気3.5倍以上": lambda r: r["fav"] >= 3.5,
           "非根幹": lambda r: r["dist"] not in ROOTD, "14頭以上": lambda r: r["n"] >= 14}
BETS = ["均等", "払戻均等", "30倍未満を外す"]


def prep(sfx):
    os.environ["ROWS_SFX"] = sfx
    import importlib
    import flag_ticket_search as F
    importlib.reload(F)
    import kametani_formation as KF
    races = F.load()
    os.environ["TEN"] = "time"
    ten = KF.early_rank_time(races)
    out = []
    for r in races:
        rt = KF.real_trio(r["rid"])
        hs = [h for h in r["horses"] if h["odds"] and h["odds"] > 0]
        if not rt or len(hs) < 8:
            continue
        w = [k for k, v in r["pay"]["3連複"].items()]
        if not w:
            continue
        out.append(dict(rid=r["rid"], per=F.period(r["date"]), dist=r["dist"], n=len(hs), fav=min(h["odds"] for h in hs),
                        hs=[(h["num"], h["pop"], h["odds"], h["sc"]) for h in hs], ten=ten.get(r["rid"], {}), trio=rt,
                        win={k: v for k, v in r["pay"]["3連複"].items()}))
    return out


def cols(r, ax, c2n, c3n):
    T, X, two = ax
    hs = r["hs"]
    cand = sorted([h for h in hs if h[3] >= T and h[2] >= X], key=lambda h: (-h[3], h[2]))
    if len(cand) < (2 if two else 1):
        return None
    c1 = [h[0] for h in cand[:2 if two else 1]]
    bypop = [h[0] for h in sorted(hs, key=lambda h: h[1])]
    byflag = [h[0] for h in sorted(hs, key=lambda h: (-h[3], h[2])) if h[0] not in c1]
    byten = [n for n, k in sorted(r["ten"].items(), key=lambda x: x[1])]
    if c2n == "人気1-3": c2 = bypop[:3]
    elif c2n == "人気1-4": c2 = bypop[:4]
    elif c2n == "人気1-5": c2 = bypop[:5]
    elif c2n == "フラグ上位3": c2 = byflag[:3]
    elif c2n == "テン上位3": c2 = byten[:3]
    else: c2 = list(dict.fromkeys(bypop[:3] + byflag[:2]))
    if c3n == "全頭": c3 = [h[0] for h in hs]
    elif c3n == "人気1-9": c3 = bypop[:9]
    elif c3n == "単勝50倍未満": c3 = [h[0] for h in hs if h[2] < 50]
    elif c3n == "フラグ+2以上": c3 = [h[0] for h in hs if h[3] >= 2]
    else: c3 = byten[:9]
    return c1, c2, c3


def combos(c1, c2, c3, two):
    if two:
        a, b = c1
        return {tuple(sorted((a, b, c))) for c in set(c2) | set(c3) if c not in (a, b)}
    a = c1[0]
    return {tuple(sorted((a, x, y))) for x in c2 for y in c3 if len({a, x, y}) == 3}


def key(cb):
    return "-".join(map(str, cb))


def work(args):
    ax, c2n, c3n, races = args
    res = {}
    for r in races:
        cc = cols(r, ax, c2n, c3n)
        if not cc:
            continue
        cbs = combos(*cc, ax[2])
        if not cbs:
            continue
        od = {cb: r["trio"].get(key(cb)) or 0 for cb in cbs}
        for fn, f in FILTERS.items():
            if not f(r):
                continue
            for bet in BETS:
                if bet == "30倍未満を外す":
                    use = [cb for cb in cbs if od[cb] >= 30]
                else:
                    use = list(cbs)
                if not use:
                    continue
                if bet == "払戻均等":
                    w = {cb: 1 / od[cb] for cb in use if od[cb] > 0}
                    if not w:
                        continue
                    ws = sum(w.values()); budget = 100 * len(use)
                    stake = {cb: max(100, round(budget * w[cb] / ws / 100) * 100) for cb in w}
                else:
                    stake = {cb: 100 for cb in use}
                cost = sum(stake.values())
                ret = sum(r["win"].get(key(cb), 0) * stake[cb] // 100 for cb in stake)
                a = res.setdefault((fn, bet, r["per"]), [0, 0, 0, 0])
                a[0] += 1; a[1] += cost; a[2] += ret; a[3] += ret > 0
    return (ax, c2n, c3n), res


def evaluate(races, workers):
    jobs = [(ax, c2, c3, races) for ax in AXES for c2 in C2S for c3 in C3S]
    with Pool(workers) as p:
        return dict(p.map(work, jobs, chunksize=4))


def main():
    workers = int(sys.argv[1]) if len(sys.argv) > 1 else 4
    tr = evaluate([r for r in prep("_items") if r["per"] in ("2021-23", "2024")], workers)
    te = evaluate(prep("_oos"), workers)
    rows = []
    for st, res in tr.items():
        for fn in FILTERS:
            for bet in BETS:
                a, b = res.get((fn, bet, "2021-23")), res.get((fn, bet, "2024"))
                if not a or not b or a[0] < 100 or b[0] < 40:
                    continue
                ra, rb = a[2] / a[1], b[2] / b[1]
                if ra < 1.10 or rb < 1.10:
                    continue
                t = te.get(st, {}).get((fn, bet, "2025-26/9"), [0, 0, 0, 0]); l = te.get(st, {}).get((fn, bet, "実戦10月〜"), [0, 0, 0, 0])
                rows.append((st, fn, bet, ra, rb, a[0] + b[0], (t[2] / t[1]) if t[1] else None, t[0], (t[3] / t[0]) if t[0] else 0,
                             (l[2] / l[1]) if l[1] else None, l[0], (a[1] + b[1]) / max(a[0] + b[0], 1)))
    rows.sort(key=lambda x: -(x[6] or 0))
    L = ["# 3連複フォーメーションの組み方の総当たり（tools/formation_search.py, 2026-11-08）", "",
         "JRA の実際の最終オッズと払戻で採点。2021-23・2024 の両方で回収110%以上の組み方だけを残し、2025-26/9（材料を2021-24だけで選んだフラグ）と実戦10月〜で答え合わせ。",
         "1列目: フラグ点T以上・単勝X倍以上の上位1頭（2頭軸は上位2頭）。2頭軸は 1列目2頭×（2列目∪3列目）。払戻均等は1点100円×点数の予算を実オッズに反比例して配分。", "",
         f"候補 {len(rows)} 件（{len(AXES) * len(C2S) * len(C3S) * len(FILTERS) * len(BETS)} 通りのうち）", "",
         "| 1列目 | 2列目 | 3列目 | 絞り込み | 買い方 | 2021-23 | 2024 | 2025-26/9（未来を見ない） | レース | 的中 | 実戦10月〜 | レース | 1レースの投資 |", "|---|---|---|---|---|---|---|---|---|---|---|---|---|"]
    for st, fn, bet, ra, rb, n, rt, nt, ht, rl, nl, cost in rows[:80]:
        (T, X, two), c2, c3 = st
        f = lambda v: "-" if v is None else f"{v:.0%}"
        L.append(f"| +{T}・{X}倍{'・2頭軸' if two else ''} | {c2} | {c3} | {fn} | {bet} | {ra:.0%} | {rb:.0%} | **{f(rt)}** | {nt} | {ht:.0%} | {f(rl)} | {nl} | {cost:,.0f}円 |")
    (ROOT / "docs" / "analysis" / "formation_search.md").write_text("\n".join(L) + "\n", encoding="utf-8")
    print("\n".join(L[:40]))


if __name__ == "__main__":
    main()
