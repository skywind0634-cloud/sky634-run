"""コラムの「血×条件」で、3連複・ワイドの紐（相手）をどう選ぶと的中・回収が良いか（2026-10-27, ユーザー指示）.

ユーザー指摘「単勝の回収率だけで判断するな。人気馬は0.9以上なら3連複・ワイドの紐として拾うべきでは。0.9以上を入れたときの的中率を調べろ」。

- 血の評価は 2021-24 だけで決める（tools/trait_check.py の evaluate の 2021-23・2024 の条件内A/E）。2025-26 のレースで試す（後から見た当てはめにならないように）。
- 各馬の「血の点」＝その馬が持つ血 × 今回の条件（ペースはレース前に分からないので除く）に当てはまる主張の、2021-24 条件内A/E の最大値（2期とも40走以上のものだけ）。
  当てはまる主張が無い馬は「材料なし」。
- まず人気帯 × 血の点で、2025-26 の3着内率・A/E を出す（紐に残すべきかの直接の答え）。
- 次に、紐の選び方ごとに、1番人気・2番人気を軸にした3連複（軸2頭−紐）と、1番人気−紐のワイドを実際の払戻で計算する。
使い方: python3 tools/trait_himo_check.py <ped5_full.json> → docs/analysis/trait_himo_check.md
"""
import json
import sqlite3
import sys
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
import trait_check as T  # noqa: E402

PACE = {"瞬発", "持続"}


def main(pf):
    P = json.loads(Path(pf).read_text(encoding="utf-8"))
    claims = []
    for cf in ("claims_mochida.json", "claims_sakagami.json"):
        d = json.loads((ROOT / "data" / "knowledge" / cf).read_text(encoding="utf-8"))
        claims += [dict(x, source=d["_meta"]["source"]) for x in d["claims"] if x["n_art"] >= 3 and x["cond"] not in PACE]
    claims = [dict(x, entity=x["entity"] + v, base=x["entity"]) for x in claims
              for v in (("", "（3代以内）", "（クロス）") if not x["entity"].startswith("父=") else ("",))]
    c = sqlite3.connect(ROOT / "data" / "keiba.db")
    res = T.evaluate(claims, P, c)
    # (entity, cond) → 2021-24 の条件内A/E（2期とも数がある主張だけ。向きは問わず実績の数字を使う）
    # 血の点は「同じ血の他の条件比」（2021-24 の2期の悪い方）。在来の大半の馬が持つ血（3割以上）は区別にならないので除く
    score = {}
    for r in res:
        a = r["ratio_3"][:2]
        if None in a:
            continue
        score[(r["entity"], r["cond"])] = min(a)
    ents = {e for e, _ in score}
    pos = P["pos"]; gen = [len(p) for p in pos]
    tags = {}
    for hid, anc in P["horses"].items():
        t = set()
        for e in ents:
            if e.startswith("父="):
                if anc and anc[0] == e[2:]:
                    t.add(e)
                continue
            b = e.split("（")[0]
            gs = [g for g, a in zip(gen, anc) if a == b]
            if gs and (e == b or (e.endswith("（3代以内）") and min(gs) <= 3) or (e.endswith("（クロス）") and len(gs) >= 2)):
                t.add(e)
        tags[hid] = t
    cnt = defaultdict(int)
    for t in tags.values():
        for e in t:
            cnt[e] += 1
    common = {e for e, v in cnt.items() if v >= 0.3 * len(tags)}
    score = {k: v for k, v in score.items() if k[0] not in common}
    tags = {h: t - common for h, t in tags.items()}
    races = {r[0]: r[1:] for r in c.execute(
        "select race_id,date,course,surface,distance,going,layout,payouts from races where date>='2025-01-01' and surface in ('芝','ダ') and payouts like '%3連複%'")}
    by_race = defaultdict(list)
    for rid, hid, fin, pop, sex, age, num in c.execute("select race_id,horse_id,finish,popularity,sex,age,number from results where finish and popularity"):
        if rid in races:
            by_race[rid].append((hid, fin, pop, sex, age, num))
    # 人気からの3着内の見込み（2021-24）
    base = defaultdict(lambda: [0, 0])
    for fin, pop in c.execute("select r.finish,r.popularity from results r join races x using(race_id) where x.date<'2025-01-01' and r.finish and r.popularity"):
        b = base[min(pop, 16)]; b[0] += 1; b[1] += fin <= 3
    exp = {k: v[1] / v[0] for k, v in base.items()}

    def band(s):
        if s is None:
            return "材料なし"
        return "〜0.90" if s < 0.9 else "0.90〜1.00" if s < 1.0 else "1.00〜1.08" if s < 1.08 else "1.08〜"
    BANDS = ["材料なし", "〜0.90", "0.90〜1.00", "1.00〜1.08", "1.08〜"]
    # 血の点＝当てはまる主張のうち一番良い比。ほかに一番悪い比も見る（「血が条件に合わない」馬を外すとどうなるか）
    POPS = [("1-3人気", 1, 3), ("4-5人気", 4, 5), ("6-8人気", 6, 8), ("9人気-", 9, 99)]
    agg = defaultdict(lambda: [0, 0.0, 0])
    rs = []
    for rid, hs in by_race.items():
        d, co, su, dist, go, lay, pay = races[rid]
        if len(hs) < 8:
            continue
        hh = []
        for hid, fin, pop, sex, age, num in hs:
            cs = T.conds((co, su, dist, go, lay, None, sex, age)) - PACE
            ss = [score[(e, cn)] for e in tags.get(hid, ()) for cn in cs if (e, cn) in score]
            s = max(ss) if ss else None
            hh.append(dict(num=num, fin=fin, pop=pop, s=s, lo=min(ss) if ss else None))
            pb = next(n for n, lo, hi in POPS if lo <= pop <= hi)
            a = agg[(pb, band(s))]; a[0] += fin <= 3; a[1] += exp[min(pop, 16)]; a[2] += 1
        rs.append((rid, hh, json.loads(pay)))
    L = ["# コラムの「血×条件」で紐を選ぶと、3連複・ワイドの的中・回収はどうなるか（tools/trait_himo_check.py）", "",
         "血の評価は2021-24だけで決め、2025-01〜2026-10 のレース（第7R以降・8頭以上）で試した。血の点＝その馬の血×今回の条件に当てはまる主張の、同じ血の他の条件比（2021-24の2期の悪い方）の最大値。3割以上の馬が持つ血（サンデー・Halo 等）は除く。", "",
         "## 人気帯 × 血の点 → 2025-26 の3着内率", "", "| 人気 | 血の点 | 走数 | 3着内率 | A/E |", "|---|---|---|---|---|"]
    for pb, _, _ in POPS:
        for b in BANDS:
            a = agg[(pb, b)]
            if a[2]:
                L.append(f"| {pb} | {b} | {a[2]} | {a[0] / a[2]:.1%} | {a[0] / a[1]:.2f} |")

    def sim(name, himo):
        """軸＝1・2番人気の2頭、紐＝himo(馬リスト) → 3連複（軸2頭−紐）。ワイド＝1番人気−紐."""
        n = hit3 = pay3 = nw = hitw = payw = 0
        days = 0
        for rid, hh, pay in rs:
            ax = [h for h in hh if h["pop"] in (1, 2)]
            if len(ax) != 2:
                continue
            days += 1
            hm = [h for h in hh if h["pop"] > 2 and himo(h)]
            top = {h["num"] for h in hh if h["fin"] <= 3}
            t3 = {"-".join(sorted(k.split("-"), key=int)): v for k, v in pay.get("3連複", [])}
            wd = {"-".join(sorted(k.split("-"), key=int)): v for k, v in pay.get("ワイド", [])}
            a1 = next(h for h in ax if h["pop"] == 1)
            for h in hm:
                k = "-".join(str(x) for x in sorted([ax[0]["num"], ax[1]["num"], h["num"]]))
                n += 1
                if k in t3:
                    hit3 += 1; pay3 += t3[k]
                kw = "-".join(str(x) for x in sorted([a1["num"], h["num"]]))
                nw += 1
                if kw in wd:
                    hitw += 1; payw += wd[kw]
        return (f"| {name} | {n / max(days, 1):.1f} | {hit3 / max(days, 1):.1%} | {pay3 / max(n * 100, 1):.0%} "
                f"| {hitw / max(days, 1):.1%} | {payw / max(nw * 100, 1):.0%} |")
    L += ["", "## 紐の選び方 → 3連複（1・2番人気の2頭軸−紐）・ワイド（1番人気−紐）", "",
          "的中率はレースあたり（そのレースで1点でも当たったか）。回収率は払戻÷購入額。", "",
          "| 紐 | 1レースの点数 | 3連複 的中率 | 3連複 回収率 | ワイド 的中率 | ワイド 回収率 |", "|---|---|---|---|---|---|"]
    ok = lambda h, t: h["s"] is not None and h["s"] >= t
    L += [sim("3〜5番人気 全部", lambda h: h["pop"] <= 5),
          sim("3〜5番人気のうち血の点0.90以上", lambda h: h["pop"] <= 5 and ok(h, 0.9)),
          sim("3〜5番人気のうち血の点0.90未満・材料なし", lambda h: h["pop"] <= 5 and not ok(h, 0.9)),
          sim("3〜6番人気 全部", lambda h: h["pop"] <= 6),
          sim("3〜5番人気全部＋6〜8番人気の血の点0.90以上", lambda h: h["pop"] <= 5 or (h["pop"] <= 8 and ok(h, 0.9))),
          sim("3〜5番人気全部＋6〜8番人気の血の点1.00以上", lambda h: h["pop"] <= 5 or (h["pop"] <= 8 and ok(h, 1.0))),
          sim("3〜5番人気全部＋6〜8番人気の血の点1.08以上", lambda h: h["pop"] <= 5 or (h["pop"] <= 8 and ok(h, 1.08))),
          sim("3〜8番人気 全部", lambda h: h["pop"] <= 8),
          sim("6〜8番人気の血の点0.90以上だけ", lambda h: 6 <= h["pop"] <= 8 and ok(h, 0.9)),
          sim("6〜8番人気の血の点0.90未満・材料なしだけ", lambda h: 6 <= h["pop"] <= 8 and not ok(h, 0.9)),
          sim("9番人気以下の血の点1.00以上だけ", lambda h: h["pop"] >= 9 and ok(h, 1.0)),
          sim("3〜5番人気のうち、合わない血（比0.90未満）を持つ馬を外す", lambda h: h["pop"] <= 5 and not (h["lo"] is not None and h["lo"] < 0.9)),
          sim("3〜5番人気全部＋6〜8番人気で合わない血（比0.90未満）が無い馬", lambda h: h["pop"] <= 5 or (h["pop"] <= 8 and not (h["lo"] is not None and h["lo"] < 0.9)))]
    (ROOT / "docs" / "analysis" / "trait_himo_check.md").write_text("\n".join(L) + "\n", encoding="utf-8")
    print("\n".join(L))


if __name__ == "__main__":
    main(sys.argv[1])
