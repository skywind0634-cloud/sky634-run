"""★特推しの「8番人気以下」を外したら・倍率で区切ったらどうなるか（2026-11-08 ユーザー指示「特推しってどういう時につくの？」「検証してみて」）.
本番と同じ evaluate_race → race_digest で、各馬の 血統要素・専門家・検証済み・開催×血統○・走る条件の点 を記録し（data/cache/boost_rows.json）、
★血統穴の人気の下限（8番人気以下 / なし / 4番人気以下）と単勝の倍率帯を変えて、★特推しの買い目（ワイド1〜3番人気＋3連複 1番人気−2・3番人気）の成績を
前半（学習期間に近い）・後半・実戦（2026-10〜）で比べる。
使い方: python3 tools/boost_check.py [並列数]   （rows があれば集計だけ: python3 tools/boost_check.py report）"""
import json, sqlite3, sys
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
_connect = sqlite3.connect
sqlite3.connect = lambda *a, **k: _connect(*a, **{**k, "timeout": 300})
sys.path.insert(0, str(ROOT))
START, END = "2024-01-01", "2026-11-01"
OUT = ROOT / "data" / "cache" / ("boost_rows" + __import__("os").environ.get("BOOST_SFX", "") + ".json")


def run(args):
    start, end, before = args
    from keiba import analysis, db, digest
    from keiba.model import evaluate_race
    from keiba.validate import race_cards, _learn_before
    conn = db.connect()
    st = analysis.build_stats(conn, before=before)
    _learn_before(conn, before)
    out = []
    for card, fin, pay in race_cards(conn, start, end):
        if not all(e.get("popularity") for e in card["entries"]) or not all(e.get("_odds") for e in card["entries"]):
            continue
        for e in card["entries"]:
            e["odds"] = e["_odds"]
        try:
            ev = evaluate_race(card, st, conn, n_sims=0)
            d = digest.race_digest(ev, digest.flag_scores(card, ev))
            stg = {num for num, t in digest.stage_blood_horses(card, ev) if "○" in t or "◎" in t}
        except Exception:  # noqa: BLE001
            continue
        exp = {h.number for h, _ in d["専門家"]}
        ver = {h.number for h, _ in d["検証済み"]}
        val = {h.number for h, _ in d["妙味条件"]}  # 2026-11-08 妙味条件の集まり（tools/set_formation_search.py）
        horses = [dict(num=h.number, pop=h.pop_rank, odds=h.odds, fin=fin.get(h.number), bu=round(h.blood_upside or 0, 4),
                       oof=bool(h.out_of_form), cs=round(h.cond_score or 0, 3), exp=h.number in exp, ver=h.number in ver,
                       stg=h.number in stg, val=h.number in val) for h in ev]
        out.append(dict(date=card["date"], rid=card["race_id"], grade=card.get("grade"), n=len(ev), horses=horses,
                        wide={k: v for k, v in pay.get("ワイド", [])}, trio={k: v for k, v in pay.get("3連複", [])}))
    return out


def collect(workers):
    import datetime as dt, shutil
    from multiprocessing import Pool
    from keiba import db, value as V
    conn = db.connect()
    bak = V.COND_PATH.with_suffix(".bak")
    if V.COND_PATH.exists() and not bak.exists():
        shutil.copy(V.COND_PATH, bak)
    try:
        V.build_cond([r for r in V.load(conn) if r["date"] < START])
        d0, d1 = dt.date.fromisoformat(START), dt.date.fromisoformat(END)
        chunks, d = [], d0
        while d <= d1:
            e = min(d + dt.timedelta(days=20), d1)
            chunks.append((d.isoformat(), e.isoformat(), START)); d = e + dt.timedelta(days=1)
        with Pool(workers) as pool:
            parts = pool.map(run, chunks, chunksize=1)
    finally:
        if bak.exists():
            shutil.move(bak, V.COND_PATH)
    rows = [r for p in parts for r in p]
    json.dump(rows, open(OUT, "w"), ensure_ascii=False)
    return rows


def stars(r, floor, max_n=3):
    ls = sorted((h for h in r["horses"] if (h["pop"] or 0) >= floor and h["bu"] > 0 and not h["oof"]), key=lambda h: -h["bu"])
    if not ls:
        return []
    best = ls[0]["bu"]
    return [ls[0]] + [h for h in ls[1:max_n] if h["bu"] >= max(0.3, 0.6 * best)]


def boosts(r, floor, odds_lo, odds_hi, need_n13=True):
    out = []
    graded = r["grade"] in ("G1", "G2", "G3")
    for h in stars(r, floor):
        o = h["odds"] or 999
        if not (odds_lo <= o < odds_hi):
            continue
        if not graded and need_n13 and r["n"] < 13:
            continue
        why = h["exp"] or h["ver"] or h["stg"] or (7 <= (h["pop"] or 0) <= 9 and h["cs"] >= 0.4)
        if why:
            out.append(h)
    return out


def tickets(r, h):
    pop = {x["pop"]: x["num"] for x in r["horses"] if x["pop"]}
    w = ["-".join(map(str, sorted((pop[p], h["num"])))) for p in (1, 2, 3) if p in pop and pop[p] != h["num"]]
    t = ["-".join(map(str, sorted((pop[1], pop[p], h["num"])))) for p in (2, 3) if 1 in pop and p in pop and h["num"] not in (pop[1], pop[p])]
    return w, t


def period(d):
    return "前半2024" if d < "2025-01-01" else "後半2025-26/9" if d < "2026-10-01" else "実戦2026/10〜"


VARIANTS = [
    ("今（8番人気以下・50倍未満）", 8, 0, 50),
    ("人気の下限なし・50倍未満", 1, 0, 50),
    ("人気の下限なし・10〜50倍", 1, 10, 50),
    ("人気の下限なし・15〜50倍", 1, 15, 50),
    ("人気の下限なし・20〜50倍", 1, 20, 50),
    ("人気の下限なし・10〜30倍", 1, 10, 30),
    ("人気の下限なし・30倍未満", 1, 0, 30),
    ("4番人気以下・50倍未満", 4, 0, 50),
    ("8番人気以下・30倍未満", 8, 0, 30),
    ("8番人気以下・20倍未満", 8, 0, 20),
    ("8番人気以下・20〜50倍", 8, 20, 50),
]


def report(rows):
    L = ["# ★特推しの人気の下限・倍率帯の見直し（tools/boost_check.py, 2026-11-08）", "",
         f"本番と同じ予想を {START}〜{END} で作り直した（学習は {START} より前のデータだけ）。★特推し＝★血統穴が 専門家・検証済み・開催×血統○・7〜9番人気の走る条件 のどれかと重なる馬。",
         "買い目は今と同じ ワイド→1〜3番人気（3点）＋3連複 1番人気−2・3番人気−その馬（2点）、1点100円。A/E＝3着内の実数÷人気からの見込み。", "",
         "| 区切り | 期間 | 頭数 | 3着内率 | 3着内A/E | 単勝回収 | ワイド回収 | 3連複回収 | 合計回収 | 的中（1点でも） |", "|---|---|---|---|---|---|---|---|---|---|"]
    base = defaultdict(lambda: [0, 0])
    for r in rows:
        for h in r["horses"]:
            if h["fin"] and h["pop"]:
                p = min(h["pop"], 16); base[p][0] += 1; base[p][1] += h["fin"] <= 3
    e3 = {k: v[1] / v[0] for k, v in base.items()}
    summary = []
    for name, floor, lo, hi in VARIANTS:
        agg = defaultdict(lambda: [0, 0, 0.0, 0, 0, 0, 0, 0, 0, 0])  # n, top3, exp, tan, wide_bet, wide_ret, trio_bet, trio_ret, hit_races, races
        for r in rows:
            for h in boosts(r, floor, lo, hi):
                if not h["fin"]:
                    continue
                w, t = tickets(r, h)
                wr = sum(r["wide"].get(k, 0) for k in w); tr = sum(r["trio"].get(k, 0) for k in t)
                tan = 0
                if h["fin"] == 1:
                    tan = round((h["odds"] or 0) * 100)
                for k in (period(r["date"]), "全体"):
                    a = agg[k]
                    a[0] += 1; a[1] += h["fin"] <= 3; a[2] += e3[min(h["pop"], 16)]; a[3] += tan
                    a[4] += 100 * len(w); a[5] += wr; a[6] += 100 * len(t); a[7] += tr; a[8] += (wr + tr) > 0; a[9] += 1
        for k in ("前半2024", "後半2025-26/9", "実戦2026/10〜", "全体"):
            a = agg.get(k)
            if not a or not a[0]:
                L.append(f"| {name} | {k} | 0 | - | - | - | - | - | - | - |"); continue
            bet = a[4] + a[6]
            L.append(f"| {name} | {k} | {a[0]} | {a[1] / a[0]:.1%} | {a[1] / a[2]:.2f} | {a[3] / a[0]:.0f}% | {a[5] / max(a[4], 1):.0%} | "
                     f"{a[7] / max(a[6], 1):.0%} | {(a[5] + a[7]) / max(bet, 1):.0%} | {a[8] / a[9]:.0%} |")
        summary.append((name, {k: agg[k] for k in agg}))
    L += ["", "## 前半・後半・実戦の合計回収（ワイド＋3連複）", "", "| 区切り | 前半2024 | 後半2025-26/9 | 実戦2026/10〜 | 頭数（前/後/実） |", "|---|---|---|---|---|"]
    for name, ag in summary:
        def rr(k):
            a = ag.get(k)
            return f"{(a[5] + a[7]) / max(a[4] + a[6], 1):.0%}" if a and a[0] else "-"
        L.append(f"| {name} | {rr('前半2024')} | {rr('後半2025-26/9')} | {rr('実戦2026/10〜')} | "
                 + "/".join(str(ag[k][0]) if k in ag else "0" for k in ("前半2024", "後半2025-26/9", "実戦2026/10〜")) + " |")
    (ROOT / "docs" / "analysis" / "boost_check.md").write_text("\n".join(L) + "\n", encoding="utf-8")
    print("\n".join(L))


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "collect":
        collect(int(sys.argv[2]) if len(sys.argv) > 2 else 4)
    elif len(sys.argv) > 1 and sys.argv[1] == "report":
        report(json.load(open(OUT)))
    else:
        report(collect(int(sys.argv[1]) if len(sys.argv) > 1 else 4))
