import json, random, datetime as dt
from collections import defaultdict
from keiba import strategy as S
data = json.loads(S.CACHE.read_text())
TAKE = {"単勝": .8, "複勝": .8, "ワイド": .775, "馬連": .775, "三連複": .775}
def est_pay(kind, hs, pm):
    return 100 * TAKE[kind] / max(S.ticket_prob(kind, hs, pm), 1e-6)
def pick(r, th=1.3, pmin=4, pmax=9, n=1):
    v = sorted((h for h in r["horses"] if pmin <= (h["pop"] or 0) <= pmax and S.ratio(h) >= th and not S.danger(h)), key=lambda h: -S.ratio(h))
    return v[:n]
def axis(r):
    hs = sorted(r["horses"], key=lambda h: -h["p"])
    return next((h for h in hs if not S.danger(h)), hs[0])
def make(tan=False, fuku=False, wide=False, trio=0, trio_min=2000, th=1.3, nval=1, ev=0.0, umaren=False):
    def f(r):
        V = pick(r, th, n=nval)
        if not V: return [], None
        A = axis(r)
        pm = {h["num"]: h["pm"] for h in r["horses"]}; pp = {h["num"]: h["p"] for h in r["horses"]}
        T = []
        for v in V:
            if tan: T.append(("単勝", (v["num"],)))
            if fuku: T.append(("複勝", (v["num"],)))
            if v is not A:
                if wide: T.append(("ワイド", (A["num"], v["num"])))
                if umaren: T.append(("馬連", (A["num"], v["num"])))
            if trio:
                others = [h for h in sorted(r["horses"], key=lambda h: -h["p"]) if h["num"] not in (A["num"], v["num"]) and not S.danger(h)][:6]
                c = []
                for x in others:
                    t = tuple(sorted((A["num"], v["num"], x["num"])))
                    if A is v: continue
                    if est_pay("三連複", t, pm) >= trio_min and S.ticket_prob("三連複", t, pp) >= ev * S.ticket_prob("三連複", t, pm):
                        c.append(("三連複", t))
                T += c[:trio]
        T = list(dict.fromkeys(T))
        return (T, 1) if T else ([], None)
    return f
def metrics(d, f):
    seq = []; weeks = defaultdict(lambda: [0, 0])
    for r in d:
        T, s = f(r)
        if s is None: continue
        c = 100 * len(T); b = sum(S.payout(k, h, r["pay"]) for k, h in T)
        seq.append((c, b)); wk = dt.date.fromisoformat(r["date"]).isocalendar()[:2]
        weeks[wk][0] += c; weeks[wk][1] += b
    if not seq: return None
    C = sum(c for c, _ in seq); B = sum(b for _, b in seq)
    bal = peak = mdd = 0; streak = mstreak = 0
    for c, b in seq:
        bal += b - c; peak = max(peak, bal); mdd = max(mdd, peak - bal)
        streak = streak + 1 if b == 0 else 0; mstreak = max(mstreak, streak)
    wl = list(weeks.values())
    rnd = random.Random(1); prof4 = 0
    for _ in range(4000):
        s = [rnd.choice(wl) for _ in range(4)]
        prof4 += sum(x[1] for x in s) >= sum(x[0] for x in s)
    return dict(n=len(seq), pts=C // 100, roi=B / C, hit=sum(b > 0 for _, b in seq) / len(seq), mdd=mdd / 100,
                streak=mstreak, wk=sum(x[1] >= x[0] for x in wl) / len(wl), m4=prof4 / 4000, perwk=C / 100 / len(wl))
S1 = {
 "単勝": make(tan=True),
 "単複": make(tan=True, fuku=True),
 "複勝": make(fuku=True),
 "ワイド軸-妙味": make(wide=True),
 "単+ワイド": make(tan=True, wide=True),
 "単複+ワイド": make(tan=True, fuku=True, wide=True),
 "馬連軸-妙味": make(umaren=True),
 "三連複(軸-妙味-他,2000円~)x4": make(trio=4),
 "三連複x4 EV1": make(trio=4, ev=1.0),
 "単+ワイド+三連複x4": make(tan=True, wide=True, trio=4),
 "単複+ワイド+三連複x4": make(tan=True, fuku=True, wide=True, trio=4),
 "単+ワイド+三連複x4 EV1": make(tan=True, wide=True, trio=4, ev=1.0),
 "単+ワイド(妙味2頭)": make(tan=True, wide=True, nval=2),
 "単(1.15)+ワイド": make(tan=True, wide=True, th=1.15),
}
h1 = [r for r in data if r["date"] < "2026-04-01"]; h2 = [r for r in data if r["date"] >= "2026-04-01"]
for nm, f in {}.items():
    row = []
    for d in (h1, h2, data):
        m = metrics(d, f)
        row.append(f"回収{m['roi']:4.0%} 的中{m['hit']:4.0%}" )
    m = metrics(data, f)
    print(f"{nm:24s} | 前半 {row[0]} | 後半 {row[1]} | 通年 {row[2]} 週{m['perwk']:4.0f}点 最大連敗{m['streak']:3d} 最大DD{m['mdd']:6.0f}点 週プラス{m['wk']:4.0%} 4週プラス確率{m['m4']:4.0%}", flush=True)
print("---- 追加")
def trioV(k=4, mn=2000, ev=0.0, th=1.3):
    def f(r):
        V = pick(r, th)
        if not V: return [], None
        v = V[0]; pm = {h["num"]: h["pm"] for h in r["horses"]}; pp = {h["num"]: h["p"] for h in r["horses"]}
        top = [h for h in sorted(r["horses"], key=lambda h: -h["p"]) if h is not v and not S.danger(h)][:k]
        from itertools import combinations
        T = []
        for a, b in combinations(top, 2):
            t = tuple(sorted((v["num"], a["num"], b["num"])))
            if est_pay("三連複", t, pm) >= mn and S.ticket_prob("三連複", t, pp) >= ev * S.ticket_prob("三連複", t, pm):
                T.append(("三連複", t))
        return (T, 1) if T else ([], None)
    return f
def comb(*fs):
    def f(r):
        T = []
        for g in fs:
            t, s = g(r)
            if s is not None: T += t
        return (T, 1) if T else ([], None)
    return f
S2 = {"三連複 妙味軸-上位4頭(6点)": trioV(4), "三連複 妙味軸-上位5頭(10点)": trioV(5),
      "三連複 妙味軸-上位4頭 EV1": trioV(4, ev=1.0),
      "単複+三連複 妙味軸-上位4頭": comb(make(tan=True, fuku=True), trioV(4)),
      "単複(1.15)": make(tan=True, fuku=True, th=1.15),
      "単複(1.5)": make(tan=True, fuku=True, th=1.5),
      "単複 妙味2頭": make(tan=True, fuku=True, nval=2)}
for nm, f in S2.items():
    row = []
    for d in (h1, h2, data):
        m = metrics(d, f); row.append(f"回収{m['roi']:4.0%} 的中{m['hit']:4.0%}")
    m = metrics(data, f)
    print(f"{nm:24s} | 前半 {row[0]} | 後半 {row[1]} | 通年 {row[2]} 週{m['perwk']:4.0f}点 最大連敗{m['streak']:3d} 最大DD{m['mdd']:6.0f}点 週プラス{m['wk']:4.0%} 4週プラス確率{m['m4']:4.0%}", flush=True)
