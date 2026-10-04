"""注目馬一覧の「材料」の馬（本線・走る条件・★・妙味条件）で組む馬連・ワイド・三連複の検証（過去1年・前半/後半）."""
import sys
_ARGV = list(sys.argv); sys.argv = ["x", "none"]
exec(open("tools/strategy_combo.py").read()); sys.argv = _ARGV
from itertools import combinations


def materials(r, k=4, minpop=4):
    hs = r["horses"]
    st = {h["num"] for h in S.stars(hs)}
    out = []
    for h in hs:
        if S.danger(h) or (h["pop"] or 0) < minpop:
            continue
        val = 4 <= (h["pop"] or 0) <= 9 and S.ratio(h) >= 1.3 and h["cond"] > 0
        sc = (3 if val else 0) + (2 if h["cond"] >= 0.4 else 0) + (1 if h["num"] in st else 0) + (1 if (h["seg"] or h["edge"] > 0.15) else 0)
        if sc >= 2:
            out.append((sc + S.ratio(h) / 10, h))
    out.sort(key=lambda x: -x[0])
    return [h for _, h in out[:k]]


def box(kind, k=4, need_val=False, axis_top=False, maxN=99):
    def f(r):
        if len(r["horses"]) > maxN:
            return [], None
        M = materials(r, k)
        if len(M) < (2 if kind != "三連複" else 3):
            return [], None
        if need_val and not any(4 <= (h["pop"] or 0) <= 9 and S.ratio(h) >= 1.3 and h["cond"] > 0 for h in M):
            return [], None
        nums = [h["num"] for h in M]
        if axis_top:   # 人気上位（モデル1位・危険でない）を加える
            A = next(h for h in sorted(r["horses"], key=lambda h: -h["p"]) if not S.danger(h))
            if A["num"] not in nums:
                nums = [A["num"]] + nums
        n = 3 if kind == "三連複" else 2
        return [(kind, c) for c in combinations(nums, n)], 1
    return f


if __name__ == "__main__" and len(sys.argv) < 2:
    for kind in ("馬連", "ワイド", "三連複"):
        for k in (3, 4, 5):
            show(f"材料BOX {kind} {k}頭", box(kind, k))
            show(f"材料BOX {kind} {k}頭＋モデル1位", box(kind, k, axis_top=True))
        show(f"材料BOX {kind} 4頭 本線馬がいるレースのみ", box(kind, 4, need_val=True))


def mid_box(kind, k=3, cond_min=0.4, maxN=99, ratio_min=1.0):
    """4〜9番人気で走る条件が強い（cond≥0.4, 人気比≥ratio_min）馬だけで組むBOX."""
    def f(r):
        if len(r["horses"]) > maxN:
            return [], None
        M = sorted((h for h in r["horses"] if 4 <= (h["pop"] or 0) <= 9 and h["cond"] >= cond_min and S.ratio(h) >= ratio_min
                    and not S.danger(h)), key=lambda h: -S.ratio(h))[:k]
        n = 3 if kind == "三連複" else 2
        if len(M) < n:
            return [], None
        return [(kind, c) for c in combinations([h["num"] for h in M], n)], 1
    return f


def run3():
    for kind in ("馬連", "ワイド", "三連複"):
        for k in (2, 3, 4):
            if kind == "三連複" and k < 3:
                continue
            show(f"中穴の材料BOX {kind} {k}頭", mid_box(kind, k))
            show(f"中穴の材料BOX {kind} {k}頭 14頭以下", mid_box(kind, k, maxN=14))
if __name__ == "__main__" and "run3" in sys.argv:
    run3()


def plus_materials(n_mat=2, wide=False, tan=True, fuku=False):
    """本線（妙味馬の単複）＋ 4〜9番人気で走る条件0.4以上の馬（本線以外, 人気比の高い順に n_mat 頭）の単勝（＋任意で複勝）、
    任意で本線馬とのワイド."""
    def f(r):
        hs = r["horses"]
        v = sorted((h for h in hs if 4 <= (h["pop"] or 0) <= 9 and S.ratio(h) >= 1.3 and not S.danger(h) and h["cond"] > 0),
                   key=lambda h: -S.ratio(h))[:1]
        M = sorted((h for h in hs if 4 <= (h["pop"] or 0) <= 9 and h["cond"] >= 0.4 and not S.danger(h)
                    and h not in v), key=lambda h: -S.ratio(h))[:n_mat]
        T = [(k, (h["num"],)) for h in v for k in ("単勝", "複勝")]
        for h in M:
            if tan:
                T.append(("単勝", (h["num"],)))
            if fuku:
                T.append(("複勝", (h["num"],)))
            if wide and v:
                T.append(("ワイド", (v[0]["num"], h["num"])))
        return (T, 1) if T else ([], None)
    return f


def run4():
    show("本線のみ", plus_materials(0))
    for n in (1, 2, 3):
        show(f"本線＋材料{n}頭の単勝", plus_materials(n))
        show(f"本線＋材料{n}頭の単複", plus_materials(n, fuku=True))
        show(f"本線＋材料{n}頭の単勝＋本線とのワイド", plus_materials(n, wide=True))
if __name__ == "__main__" and "run4" in sys.argv:
    run4()
