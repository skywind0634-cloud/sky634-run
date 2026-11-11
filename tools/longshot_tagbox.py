"""印の付いた穴馬どうしのワイドBOX・3連複BOX（少点数）を過去1年の実払戻・実オッズで検証（2026-10-18 ユーザー指摘:
「ピックアップはできていた。ワイドと3連複なら3点」）. 穴＝7番人気以下で 走る条件(0.4以上)・妙味条件・★血統穴 のどれかが付いた馬。
並べ方＝付いた数＋フラグ点。上位 k 頭のワイドBOX＋3連複BOX。レースの形（1番人気の倍率）で分ける。前半/後半＝2026-04。
使い方: python3 tools/longshot_tagbox.py → docs/analysis/longshot_tagbox.md"""
import itertools, json
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def norm(c):
    return "-".join(sorted([str(x) for x in c if str(x).isdigit()], key=int))


def main():
    sb = json.load(open(ROOT / "data" / "cache" / "strategy_backtest.json"))
    fl = json.load(open(ROOT / "data" / "cache" / "flag_backtest_rows.json"))
    F = {(r["rid"], r["pop"]): r["plus"] - r["minus"] for r in fl}
    agg = defaultdict(lambda: [[0, 0, 0, 0, 0, []] for _ in range(2)])
    for R in sb:
        hf = R["date"] >= "2026-04-01"
        P = {k: {norm(str(a).replace("－", "-").split("-")): y for a, y in v} for k, v in R["pay"].items()}
        hs = [h for h in R["horses"] if h["pop"] and h["fin"] is not None]
        o1 = next((h["odds"] for h in hs if h["pop"] == 1), None)
        if not o1:
            continue
        shape = "1人気4.1倍以上" if o1 >= 4.1 else "1人気3.1〜4.0" if o1 >= 3.1 else "1人気3.0以下"
        longs = sorted([h for h in hs if h["pop"] >= 8], key=lambda h: -h["up"])
        star = {h["num"] for h in longs[:3] if longs and h["up"] >= 0.3 and h["up"] >= 0.6 * longs[0]["up"]}
        cand = []
        for h in hs:
            if h["pop"] < 7:
                continue
            tags = (h["cond"] >= 0.4) + (h["seg"] or h["edge"] > 0.15) + (h["num"] in star)
            if tags:
                cand.append((tags + F.get((R["race_id"], h["pop"]), 0), h))
        cand.sort(key=lambda x: (-x[0], x[1]["pop"]))
        for k in (2, 3, 4):
            L = [h["num"] for _, h in cand[:k]]
            if len(L) < 2:
                continue
            for name, bs in (("ワイドBOX", {("ワイド", norm(c)) for c in itertools.combinations(L, 2)}),
                             ("3連複BOX", {("3連複", norm(c)) for c in itertools.combinations(L, 3)}),
                             ("ワイド＋3連複BOX", {("ワイド", norm(c)) for c in itertools.combinations(L, 2)} | {("3連複", norm(c)) for c in itertools.combinations(L, 3)}),
                             ("複勝", {("複勝", str(n)) for n in L})):
                if not bs:
                    continue
                rets = [P.get(t, {}).get(c, 0) for t, c in bs]
                for sh in (shape, "全レース"):
                    a = agg[(k, name, sh)][hf]
                    a[0] += 1; a[1] += len(bs); a[2] += sum(rets) > 0; a[3] += sum(rets); a[4] += max(rets)
                    if sum(rets) >= 10000:
                        a[5].append(sum(rets))
    L = ["# 印の付いた穴馬どうしのBOX（自動生成 tools/longshot_tagbox.py, 過去1年・実払戻）", "", "| 頭数 | 買い方 | 形 | レース数 | 点数/R | 的中率 | 回収率 | 1万円以上の的中 |", "|---|---|---|---|---|---|---|---|"]
    for key in sorted(agg, key=lambda k: (k[2], k[0], k[1])):
        A = agg[key]
        roi = [x[3] / max(x[1] * 100, 1) * 100 for x in A]
        L.append(f"| 上位{key[0]}頭 | {key[1]} | {key[2]} | " + "/".join(str(x[0]) for x in A) + f" | {sum(x[1] for x in A) / max(sum(x[0] for x in A), 1):.1f} | "
                 + "/".join(f"{x[2] / max(x[0], 1) * 100:.1f}%" for x in A) + " | " + "/".join(f"{r:.0f}%" for r in roi) + " | " + "/".join(str(len(x[5])) for x in A) + " |")
    (ROOT / "docs" / "analysis" / "longshot_tagbox.md").write_text("\n".join(L) + "\n", encoding="utf-8")
    print("\n".join(L))


if __name__ == "__main__":
    main()
