"""意味のある馬の集まり同士の3連複フォーメーション（2026-11-08 ユーザー「全頭買う必要はない。3番人気までとフラグ+4以上、特推し、走る条件や妙味条件、血統穴を組み合わせろ。フラグ自体は有効なんだろ」）.
集まり: P3=1〜3番人気, F3/F4/F5=フラグ点+3/+4/+5以上, STAR=★血統穴, BOOST=★特推し, RUN=走る条件（4番人気以下で走る条件0.4以上）, CB=コース別血統○（tools/course_blood_rows.py。選んだ期間に2025-26を含むので甘め）.
形: 1列目の集まり × 2列目の集まり × 3列目の集まり（列の中の馬は全部軸として使う）、またはボックス。1レース40点まで.
採点: JRA の実際の最終オッズ（払戻均等の配分）と実際の払戻。2024（フラグは flag_backtest_rows_items）と 2025-01〜26-09・実戦10月〜（材料を2021-24だけで選んだフラグ flag_backtest_rows_oos）.
★血統穴・★特推し・走る条件は data/cache/boost_rows.json（tools/boost_check.py, 2024-01〜）から.
使い方: python3 tools/set_formation_search.py → docs/analysis/set_formation_search.md"""
import itertools, json, os, sys
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
import boost_check as B  # noqa: E402
import kametani_formation as KF  # noqa: E402

MAXPTS = 40


def flag_rows(sfx):
    os.environ["ROWS_SFX"] = sfx
    import importlib
    import flag_ticket_search as F
    importlib.reload(F)
    return {r["rid"]: r for r in F.load()}, F.period


def close_map():
    """前走僅差（keiba/digest.py の close_losers と同じ: 前走 勝ち馬から0.6秒差以内の4着以下・今回 同じ芝ダ・同距離・同クラスかクラス落ち）."""
    import sqlite3
    from keiba.multi_angles import CLASS_RANK
    c = sqlite3.connect(ROOT / "data" / "keiba.db")
    win = {rid: t for rid, t in c.execute("select race_id,time_sec from results where finish=1 and time_sec is not null")}
    last, out = {}, set()
    for d, rid, hid, num, su, dist, gr, f, ts in c.execute("""select r.date,x.race_id,x.horse_id,x.number,r.surface,r.distance,r.grade,x.finish,x.time_sec
            from results x join races r on r.race_id=x.race_id where x.finish>0 order by r.date"""):
        p = last.get(hid)
        if p and p["su"] == su and p["dist"] == dist and p["f"] >= 4 and p["bh"] is not None and p["bh"] <= 0.6 \
                and CLASS_RANK.get(gr, 9) <= CLASS_RANK.get(p["gr"], 9):
            out.add((rid, num))
        last[hid] = dict(su=su, dist=dist, gr=gr, f=f, bh=(ts - win[rid]) if ts and rid in win else None)
    return out


def build():
    bp = ROOT / "data" / "cache" / ("boost_rows" + os.environ.get("BOOST_SFX", "") + ".json")
    br = {r["rid"]: r for r in json.load(open(bp))}
    fi, per = flag_rows("_items")
    fo, _ = flag_rows("_oos")
    sys.path.insert(0, str(ROOT))
    cl = close_map()
    cbr = json.load(open(ROOT / "data" / "cache" / "course_blood_rows.json"))
    cbo = ROOT / "data" / "cache" / "course_blood_rows_oos.json"
    cbr_oos = json.load(open(cbo)) if cbo.exists() and os.environ.get("CB_OOS") == "1" else None
    races = []
    for rid, b in br.items():
        d = b["date"]
        f = fo.get(rid) if d >= "2025" else fi.get(rid)
        if not f or d < "2024":
            continue
        trio = KF.real_trio(rid)
        if not trio:
            continue
        sc = {h["num"]: h["sc"] for h in f["horses"]}
        hs = [h for h in b["horses"] if h["odds"] and h["fin"]]
        if len(hs) < 8:
            continue
        pop = sorted(hs, key=lambda h: h["pop"] or 99)
        S = {"P3": {h["num"] for h in pop[:3]},
             "F3": {h["num"] for h in hs if sc.get(h["num"], 0) >= 3},
             "F4": {h["num"] for h in hs if sc.get(h["num"], 0) >= 4},
             "F5": {h["num"] for h in hs if sc.get(h["num"], 0) >= 5},
             "STAR": {h["num"] for h in B.stars(b, 8) if (h["odds"] or 999) < 50},
             "BOOST": {h["num"] for h in B.boosts(b, 8, 0, 50)},
             "RUN": {h["num"] for h in hs if (h["pop"] or 0) >= 4 and h["cs"] >= 0.4}}
        S["F4穴"] = {n for n in S["F4"] if n not in S["P3"]}
        cb = (cbr_oos if (cbr_oos is not None and d >= "2025") else cbr).get(rid, {})
        S["CB"] = {int(n) for n, (p_, m_) in cb.items() if p_ > m_ and int(n) in {h["num"] for h in hs}}  # コース別血統○
        S["CB×F3"] = S["CB"] & S["F3"]
        S["CLOSE"] = {h["num"] for h in hs if (rid, h["num"]) in cl}  # 前走僅差
        S["CLOSE×F3"] = S["CLOSE"] & S["F3"]
        S["VAL"] = {h["num"] for h in hs if h.get("val")}  # 妙味条件（2023年までで作った条件。2024以降は未来を見ない）
        S["VAL×F3"] = S["VAL"] & S["F3"]
        S["STAR+BOOST+RUN"] = S["STAR"] | S["BOOST"] | S["RUN"]
        races.append(dict(rid=rid, per=per(d), fav=min(h["odds"] for h in hs), S=S, trio=trio,
                          win={k: v for k, v in b["trio"].items()}))
    return races


def U(S, names):
    out = set()
    for n in names.split("∪"):
        out |= S[n]
    return out


SETS1 = ["F4穴", "F5", "STAR", "BOOST", "RUN", "STAR+BOOST+RUN", "F4", "CB", "CB×F3", "CLOSE", "CLOSE×F3", "VAL", "VAL×F3"]
SETS2 = ["P3", "F4", "P3∪F4", "F4∪CB", "F4∪CLOSE", "F4∪VAL"]
SETS3 = ["P3∪F4", "P3∪F3", "P3∪F4∪STAR", "P3∪F4∪RUN", "P3∪F4∪STAR+BOOST+RUN", "P3∪F3∪STAR+BOOST+RUN", "P3∪F4∪CB", "P3∪CB", "P3∪F4∪CLOSE", "P3∪CLOSE", "P3∪F4∪VAL", "P3∪VAL"]
BOXES = ["P3∪F4穴", "P3∪F5", "P3∪BOOST", "P3∪STAR", "F4", "F4∪BOOST", "P3∪F4穴∪BOOST", "F4∪CB", "P3∪CB", "CB", "F4∪CLOSE", "P3∪CLOSE", "CLOSE", "F4∪VAL", "P3∪VAL", "VAL"]
FILTERS = {"なし": lambda r: True, "1番人気2.5倍以上": lambda r: r["fav"] >= 2.5, "1番人気3.5倍以上": lambda r: r["fav"] >= 3.5}


def score(races, getcombos):
    res = defaultdict(lambda: [0, 0, 0, 0, 0, 0])  # races, eq_cost, eq_ret, al_cost, al_ret, hit
    for r in races:
        cbs = getcombos(r["S"])
        if not cbs or len(cbs) > MAXPTS:
            continue
        od = {cb: r["trio"].get("-".join(map(str, cb))) or 0 for cb in cbs}
        w = {cb: 1 / od[cb] for cb in cbs if od[cb] > 0}
        ws = sum(w.values()); budget = 100 * len(cbs)
        stake = {cb: max(100, round(budget * w[cb] / ws / 100) * 100) for cb in w} if ws else {}
        hit = [cb for cb in cbs if "-".join(map(str, cb)) in r["win"]]
        eqr = sum(r["win"]["-".join(map(str, cb))] for cb in hit)
        alr = sum(r["win"]["-".join(map(str, cb))] * stake.get(cb, 0) // 100 for cb in hit)
        for fn, f in FILTERS.items():
            if not f(r):
                continue
            for k in ((fn, r["per"]),):
                a = res[k]
                a[0] += 1; a[1] += 100 * len(cbs); a[2] += eqr; a[3] += sum(stake.values()); a[4] += alr; a[5] += bool(hit)
    return res


def main():
    races = build()
    shapes = []
    for s1 in SETS1:
        for s2 in SETS2:
            for s3 in SETS3:
                def g(S, s1=s1, s2=s2, s3=s3):
                    A, Bs, C = U(S, s1), U(S, s2), U(S, s3)
                    return {tuple(sorted((a, b, c))) for a in A for b in Bs for c in C if len({a, b, c}) == 3}
                shapes.append((f"{s1} → {s2} → {s3}", g))
    for bx in BOXES:
        def g(S, bx=bx):
            return {tuple(sorted(c)) for c in itertools.combinations(sorted(U(S, bx)), 3)}
        shapes.append((f"ボックス {bx}", g))
    rows = []
    for name, g in shapes:
        res = score(races, g)
        for fn in FILTERS:
            a, t, l = res.get((fn, "2024")), res.get((fn, "2025-26/9")), res.get((fn, "実戦10月〜"))
            if not a or not t or a[0] < 40 or t[0] < 60:
                continue
            rows.append((name, fn, a, t, l))
    def rr(a, i):
        return a[i + 1] / a[i] if a and a[i] else None
    rows.sort(key=lambda x: -min(rr(x[2], 3) or 0, rr(x[3], 3) or 0))
    f = lambda v: "-" if v is None else f"{v:.0%}"
    L = ["# 意味のある馬の集まり同士の3連複フォーメーション（tools/set_formation_search.py, 2026-11-08）", "",
         "P3=1〜3番人気、F3/F4/F5=フラグ点+3/+4/+5以上、F4穴=F4のうち1〜3番人気以外、STAR=★血統穴（50倍未満）、BOOST=★特推し、RUN=走る条件（4番人気以下）。1レース40点まで。",
         "JRA の実際の最終オッズ・払戻で採点。2024 はフラグ（flag_backtest_rows_items）、2025-26/9 と実戦は材料を2021-24だけで選んだフラグ（未来を見ない）。", "",
         "| 形 | 絞り込み | 2024 均等 / 配分 | 2025-26/9 均等 / 配分 | レース（25-26） | 的中 | 1レースの点数 | 実戦10月〜 均等 / 配分 |", "|---|---|---|---|---|---|---|---|"]
    for name, fn, a, t, l in rows[:60]:
        L.append(f"| {name} | {fn} | {f(rr(a, 1))} / {f(rr(a, 3))} | **{f(rr(t, 1))} / {f(rr(t, 3))}** | {t[0]} | {t[5] / t[0]:.0%} | {t[1] / t[0] / 100:.0f} | "
                 f"{f(rr(l, 1))} / {f(rr(l, 3))}（{l[0] if l else 0}） |")
    (ROOT / "docs" / "analysis" / "set_formation_search.md").write_text("\n".join(L) + "\n", encoding="utf-8")
    print("\n".join(L[:45]))


if __name__ == "__main__":
    main()
