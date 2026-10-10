"""2000〜3000円以上の配当を狙う組み合わせ馬券の検証（過去1年・本番と同じ予想・前半/後半）.

各レースでモデル上位K頭の組み合わせを全部作り、
 - モデルの的中確率 ÷ 市場の想定確率（人気から作った擬似オッズ, Harville）= 期待値の比
 - 市場から見た想定配当
で絞って買う。ワイド3頭BOX（妙味馬＋◎＋もう1頭）なども比べる。
"""
exec(open("tools/strategy_compare.py").read().split("S1 = {")[0])
import sys
from itertools import combinations


def gen(kind, K=7, ev=1.2, pay_min=2000, pay_max=10**9, per_race=3, maxN=99, need_value=False):
    def f(r):
        if len(r["horses"]) > maxN:
            return [], None
        pm = {h["num"]: h["pm"] for h in r["horses"]}
        pp = {h["num"]: h["p"] for h in r["horses"]}
        top = [h for h in sorted(r["horses"], key=lambda h: -h["p"]) if not S.danger(h)][:K]
        vals = {h["num"] for h in r["horses"] if 4 <= (h["pop"] or 0) <= 9 and S.ratio(h) >= 1.3 and h["cond"] > 0}
        k = 3 if kind == "三連複" else 2
        cand = []
        for c in combinations([h["num"] for h in top], k):
            if need_value and not (set(c) & vals):
                continue
            a, b = S.ticket_prob(kind, c, pp), S.ticket_prob(kind, c, pm)
            est = est_pay(kind, c, pm)
            if a >= ev * b and pay_min <= est <= pay_max:
                cand.append((a / b, c))
        cand.sort(reverse=True)
        T = [(kind, c) for _, c in cand[:per_race]]
        return (T, 1) if T else ([], None)
    return f


def wide3(maxN=99, with_star=True):
    """ワイド3頭BOX: 妙味馬（走る条件プラス）＋◎（危険でない最上位）＋ 2頭目の妙味馬 or ★ or モデル2位."""
    def f(r):
        if len(r["horses"]) > maxN:
            return [], None
        hs = sorted(r["horses"], key=lambda h: -h["p"])
        v = sorted((h for h in hs if 4 <= (h["pop"] or 0) <= 9 and S.ratio(h) >= 1.3 and not S.danger(h) and h["cond"] > 0),
                   key=lambda h: -S.ratio(h))
        if not v:
            return [], None
        A = next(h for h in hs if not S.danger(h) and h is not v[0])
        third = (v[1:2] or (S.stars(r["horses"])[:1] if with_star else []) or
                 [h for h in hs if h not in (A, v[0]) and not S.danger(h)][:1])
        if not third:
            return [], None
        trio = [v[0]["num"], A["num"], third[0]["num"]]
        if len(set(trio)) < 3:
            return [], None
        return [("ワイド", c) for c in combinations(trio, 2)], 1
    return f


h1 = [r for r in data if r["date"] < "2026-04-01"]; h2 = [r for r in data if r["date"] >= "2026-04-01"]


def show(nm, f):
    row = []
    for d in (h1, h2):
        m = metrics(d, f)
        row.append(f"{m['n']:3d}R 回収{m['roi']:4.0%} 的中{m['hit']:4.0%}" if m else "-")
    m = metrics(data, f)
    if not m:
        return
    # 当たったときの平均配当
    pays = []
    for r in data:
        T, s = f(r)
        if s is None:
            continue
        pays += [S.payout(k, c, r["pay"]) for k, c in T if S.payout(k, c, r["pay"])]
    avg = sum(pays) / len(pays) if pays else 0
    print(f"{nm:40s} | 前半 {row[0]} | 後半 {row[1]} | 通年 {m['roi']:4.0%} 的中{m['hit']:4.0%} 平均配当{avg:6.0f}円 週{m['perwk']:3.0f}点 最大連敗{m['streak']:3d} 4週+{m['m4']:4.0%}", flush=True)


if __name__ == "__main__" and "run2" not in sys.argv:
    show("ワイド3頭BOX(妙味馬+◎+3頭目)", wide3())
    show("ワイド3頭BOX 14頭以下", wide3(14))
    for kind in ("ワイド", "馬連", "三連複"):
        for ev in (1.0, 1.2, 1.5):
            for pm_, px in ((1000, 3000), (2000, 10**9), (3000, 10**9)):
                if kind == "ワイド" and pm_ >= 3000:
                    continue
                show(f"{kind} EV{ev} 想定{pm_}〜{px if px < 10**8 else ''}円 3点", gen(kind, ev=ev, pay_min=pm_, pay_max=px))
        show(f"{kind} EV1.2 2000円〜 妙味馬含む 3点", gen(kind, ev=1.2, need_value=True))
        show(f"{kind} EV1.2 2000円〜 妙味馬含む 14頭以下", gen(kind, ev=1.2, need_value=True, maxN=14))


def tanpuku(maxN=99):
    def f(r):
        if len(r["horses"]) > maxN:
            return [], None
        v = sorted((h for h in r["horses"] if 4 <= (h["pop"] or 0) <= 9 and S.ratio(h) >= 1.3 and not S.danger(h) and h["cond"] > 0),
                   key=lambda h: -S.ratio(h))[:1]
        T = [(k, (h["num"],)) for h in v for k in ("単勝", "複勝")]
        return (T, 1) if T else ([], None)
    return f


def both(*fs):
    def f(r):
        T = []
        for g in fs:
            t, s = g(r)
            if s is not None:
                T += t
        return (list(dict.fromkeys(T)), 1) if T else ([], None)
    return f


def run2():
    show("単複(全)", tanpuku())
    show("単複(全)＋馬連EV1.2/2000円〜/妙味馬含む(14頭以下)", both(tanpuku(), gen("馬連", ev=1.2, need_value=True, maxN=14)))
    show("単複(全)＋馬連EV1.2/2000円〜/妙味馬含む(全)", both(tanpuku(), gen("馬連", ev=1.2, need_value=True)))
    show("馬連EV1.2/2000円〜/妙味馬含む 14頭以下 2点", gen("馬連", ev=1.2, need_value=True, maxN=14, per_race=2))
    show("馬連EV1.2/2000円〜/妙味馬含む 14頭以下 5点", gen("馬連", ev=1.2, need_value=True, maxN=14, per_race=5))
    show("馬連EV1.5/2000円〜/妙味馬含む 14頭以下 3点", gen("馬連", ev=1.5, need_value=True, maxN=14))
    show("馬連EV1.0/2000円〜/妙味馬含む 14頭以下 3点", gen("馬連", ev=1.0, need_value=True, maxN=14))
    show("馬連EV1.2/1500円〜/妙味馬含む 14頭以下 3点", gen("馬連", ev=1.2, need_value=True, maxN=14, pay_min=1500))
    show("ワイドEV1.2/1000円〜/妙味馬含む 14頭以下 3点", gen("ワイド", ev=1.2, need_value=True, maxN=14, pay_min=1000))
if __name__ == "__main__" and "run2" in sys.argv:
    run2()
