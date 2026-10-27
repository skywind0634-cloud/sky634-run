"""コラムから拾った「血×条件」（tools/trait_mining.py）を実績で検証する（2026-10-27）.

血の保有＝5代血統表（ped5_full）にその祖先がいる／3代以内にいる／2回以上いる（クロス）の3通り（「父=X」は父がX）。同じ血を持つ馬の中で、
その条件のときの3着内A/E（人気から見込む3着内数との比）が、条件以外のときより高いか（＝その条件で浮く血の特徴か）を
3期（2021-23 / 2024 / 2025-26）で確かめる。
採用: 条件内A/Eが3期とも1.00以上・条件内÷条件外が3期とも1.00以上かつ通算1.08以上・条件内の走数300以上。
（マイナスの主張は逆向き。）条件外より良くても、人気からの見込みを下回る（条件内A/E<1.00）ものは採らない。
使い方: python3 tools/trait_check.py <ped5_full.json> <claims.json...> → data/knowledge/blood_traits.json・docs/analysis/blood_traits.md
"""
import json
import sqlite3
import sys
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BIG = {"東京"}; OUTER = {"新潟", "京都", "阪神"}; SMALL = {"中山", "福島", "小倉", "札幌", "函館"}


def per(d):
    return 0 if d < "2024-01-01" else 1 if d < "2025-01-01" else 2


def conds(r):
    """1走の条件の集合（キーは tools/trait_mining.py の COND）."""
    co, su, dist, go, lay, pace, sex, age = r
    lay = lay or ""
    s = {f"{co}{su}"}
    if go and go[0] in "稍重不":
        s.add("道悪")
    if su == "芝" and (go or "良").startswith("良"):
        s.add("高速馬場")
    if co in BIG or (co in OUTER and "外" in lay):
        s.add("大箱")
    elif co in SMALL or "内" in lay:
        s.add("小回り")
    if pace == "瞬発":
        s.add("瞬発")
    elif pace in ("持続", "消耗"):
        s.add("持続")
    if dist:
        s.add("短距離" if dist <= 1400 else "マイル" if dist <= 1800 else "長距離" if dist >= 2200 else "中距離")
    if su == "ダ":
        s.add("ダート")
    if su == "芝" and co in ("札幌", "函館"):
        s.add("洋芝")
    if sex == "牝":
        s.add("牝馬")
    if age and age >= 5:
        s.add("晩成")
    if age and age <= 3:
        s.add("早熟")
    return s


def evaluate(claims, P, c):
    pos = P["pos"]
    ents = {x["entity"] for x in claims}
    anc_ents = {x["base"] for x in claims if not x["base"].startswith("父=")}
    gen = [len(p) for p in pos]
    tags = {}
    for hid, anc in P["horses"].items():
        t = set()
        for e in anc_ents & set(anc):
            gs = [g for g, a in zip(gen, anc) if a == e]
            t.add(e)
            if min(gs) <= 3:
                t.add(e + "（3代以内）")
            if len(gs) >= 2:
                t.add(e + "（クロス）")
        if anc and anc[0] and f"父={anc[0]}" in ents:
            t.add(f"父={anc[0]}")
        if t:
            tags[hid] = t
    races = {r[0]: r[1:] for r in c.execute(
        "select race_id,date,course,surface,distance,going,layout,pace_type from races where surface in ('芝','ダ')")}
    rows = c.execute("select race_id,horse_id,finish,popularity,odds,sex,age from results where finish and popularity").fetchall()
    base = defaultdict(lambda: [0, 0])
    for rid, hid, fin, pop, od, sex, age in rows:
        if rid in races:
            b = base[min(pop, 16)]; b[0] += 1; b[1] += fin <= 3
    exp = {k: v[1] / v[0] for k, v in base.items()}
    # agg[(entity, cond, in?)][period] = [top3, exp, n, win_return]
    agg = defaultdict(lambda: [[0, 0.0, 0, 0.0] for _ in range(3)])
    need = defaultdict(set)
    for x in claims:
        need[x["entity"]].add(x["cond"])
    for rid, hid, fin, pop, od, sex, age in rows:
        if rid not in races or hid not in tags:
            continue
        d, co, su, dist, go, lay, pace = races[rid]
        cs = conds((co, su, dist, go, lay, pace, sex, age))
        p = per(d)
        for e in tags[hid]:
            for cn in need[e]:
                a = agg[(e, cn, cn in cs)][p]
                a[0] += fin <= 3; a[1] += exp[min(pop, 16)]; a[2] += 1; a[3] += (od or 0) * 100 if fin == 1 else 0
    out = []
    for x in claims:
        i, o = agg.get((x["entity"], x["cond"], True)), agg.get((x["entity"], x["cond"], False))
        if not i or not o:
            continue
        ae_i = [a[0] / a[1] if a[1] and a[2] >= 40 else None for a in i]
        ae_o = [a[0] / a[1] if a[1] and a[2] >= 40 else None for a in o]
        ni = sum(a[2] for a in i)
        ti = [sum(a[k] for a in i) for k in range(4)]; to = [sum(a[k] for a in o) for k in range(4)]
        if not ti[1] or not to[1] or ti[0] == 0 or to[0] == 0:
            continue
        AE_i, AE_o = ti[0] / ti[1], to[0] / to[1]
        sgn = 1 if x["dir"] == "+" else -1
        ok = (ni >= 300 and all(v is not None for v in ae_i + ae_o)
              and all(sgn * (a - 1) >= 0 for a in ae_i)
              and all(sgn * (a / b - 1) >= 0 for a, b in zip(ae_i, ae_o))
              and sgn * (AE_i / AE_o - 1) >= 0.08)
        out.append(dict(x, n_run=ni, ae_in=round(AE_i, 3), ae_out=round(AE_o, 3), ratio=round(AE_i / AE_o, 3),
                        ae_in_3=[round(v, 2) if v else None for v in ae_i], ratio_3=[round(a / b, 2) if a and b else None for a, b in zip(ae_i, ae_o)],
                        win_ret=round(ti[3] / ti[2], 1), ok=ok))
    return out


def main(pf, *cfs):
    P = json.loads(Path(pf).read_text(encoding="utf-8"))
    claims = []
    for cf in cfs:
        d = json.loads(Path(cf).read_text(encoding="utf-8"))
        src = d["_meta"]["source"]
        for x in d["claims"]:
            if x["n_art"] >= 3:
                claims.append(dict(x, source=src))
    c = sqlite3.connect(ROOT / "data" / "keiba.db")
    claims = [dict(x, entity=x["entity"] + v, base=x["entity"]) for x in claims
              for v in (("", "（3代以内）", "（クロス）") if not x["entity"].startswith("父=") else ("",))]
    res = evaluate(claims, P, c)
    ok = sorted([r for r in res if r["ok"]], key=lambda r: -abs(r["ratio"] - 1))
    # 同じ主張が出典違いで重なる・「3代以内」「父=」が同じ馬の集まり（走数が同じ）になるものは1つにまとめる
    seen, uniq = {}, []
    for r in ok:
        k = next((k for k in seen if k[:3] == (r["base"].removeprefix("父="), r["cond"], r["dir"]) and abs(k[3] - r["n_run"]) <= 0.03 * r["n_run"]),
                 (r["base"].removeprefix("父="), r["cond"], r["dir"], r["n_run"]))
        if k in seen:
            if r["source"] not in seen[k]["source"]:
                seen[k]["source"] += "・" + r["source"]; seen[k]["urls"] = (seen[k]["urls"] + r["urls"])[:6]; seen[k]["n_art"] += r["n_art"]
            continue
        seen[k] = r; uniq.append(r)
    ok = uniq
    # 主張通り・人気並み（条件内A/Eが3期とも1.00以上だが、同じ血の他の条件より浮くほどではない）→ 予想では△（加点しない・表示だけ）
    # 大半の馬が持つ血（サンデーサイレンス・Halo 等, 3割以上）は区別にならないので除く
    gen = [len(q) for q in P["pos"]]
    def share(ent):
        b = ent.removeprefix("父=").split("（")[0]
        n = 0
        for anc in P["horses"].values():
            gs = [g for g, a in zip(gen, anc) if a == b]
            n += bool(gs) and (ent.startswith("父=") and anc[0] == b or ent == b or ent.endswith("（3代以内）") and min(gs) <= 3 or ent.endswith("（クロス）") and len(gs) >= 2)
        return n / max(len(P["horses"]), 1)
    par, pseen = [], set()
    for r in sorted(res, key=lambda r: -r["n_art"]):
        k = (r["base"].removeprefix("父="), r["cond"])
        if (r["ok"] or r["dir"] != "+" or r["n_run"] < 300 or k in pseen or None in r["ae_in_3"]
                or not all(a >= 1.0 for a in r["ae_in_3"]) or not 0.95 <= r["ratio"] < 1.08 or share(r["entity"]) >= 0.3):
            continue
        pseen.add(k); par.append(r)
    par_keep = [{k: r[k] for k in ("entity", "cond", "dir", "source", "n_art", "n_run", "ae_in", "ratio", "ae_in_3")} for r in par]
    keep = [{k: r[k] for k in ("entity", "cond", "dir", "source", "n_art", "urls", "n_run", "ae_in", "ae_out", "ratio", "ae_in_3", "ratio_3", "win_ret")} for r in ok]
    (ROOT / "data" / "knowledge" / "blood_traits.json").write_text(json.dumps(
        {"_meta": {"description": "コラムの『血×条件』のうち実績で裏付けのあったもの（tools/trait_check.py）。本文は保存せず出典URLのみ",
                   "rule": "条件内A/E 3期とも1.00以上・条件内÷条件外 3期とも1.00以上かつ通算1.08以上・走数300以上"},
         "traits": keep, "par": par_keep}, ensure_ascii=False, indent=1), encoding="utf-8")
    L = ["# コラムの「血×条件」の検証（tools/trait_mining.py → tools/trait_check.py）", "",
         f"拾った主張 {len(claims)} 件（3記事以上で言及）のうち、実績で裏付けのあったもの {len(ok)} 件。",
         "A/E＝3着内の実数÷人気からの見込み。条件内÷条件外＝同じ血を持つ馬の中での比（1より大きいほど、その条件で浮く）。3期＝2021-23 / 2024 / 2025-26。", "",
         "## 裏付けあり（予想の材料に採用）", "",
         "| 血 | 条件 | 向き | 出典 | 記事数 | 条件内の走数 | 条件内A/E（3期） | 条件内÷条件外（3期） | 単勝回収 |", "|---|---|---|---|---|---|---|---|---|"]
    def f3(v):
        return " / ".join(f"{a:.2f}" if a else "-" for a in v)
    for r in ok:
        L.append(f"| {r['entity']} | {r['cond']} | {r['dir']} | {r['source']} | {r['n_art']} | {r['n_run']} | {r['ae_in']:.2f}（{f3(r['ae_in_3'])}） | {r['ratio']:.2f}（{f3(r['ratio_3'])}） | {r['win_ret']:.0f}% |")
    L += ["", f"## 主張通り・人気並み（{len(par)}件。条件内A/Eが3期とも1.00以上・他の条件比0.95〜1.08。予想では△で表示だけ、加点しない）", "",
          "| 血 | 条件 | 出典 | 記事数 | 条件内の走数 | 条件内A/E（3期） | 他の条件比 |", "|---|---|---|---|---|---|---|"]
    for r in par:
        L.append(f"| {r['entity']} | {r['cond']} | {r['source']} | {r['n_art']} | {r['n_run']} | {r['ae_in']:.2f}（{f3(r['ae_in_3'])}） | {r['ratio']:.2f} |")
    L += ["", "## 裏付けなし（記事数の多い順・上位80件）", "",
          "| 血 | 条件 | 向き | 出典 | 記事数 | 条件内の走数 | 条件内A/E | 条件内÷条件外（3期） |", "|---|---|---|---|---|---|---|---|"]
    for r in sorted([r for r in res if not r["ok"]], key=lambda r: -r["n_art"])[:80]:
        L.append(f"| {r['entity']} | {r['cond']} | {r['dir']} | {r['source']} | {r['n_art']} | {r['n_run']} | {r['ae_in']:.2f} | {r['ratio']:.2f}（{f3(r['ratio_3'])}） |")
    (ROOT / "docs" / "analysis" / "blood_traits.md").write_text("\n".join(L) + "\n", encoding="utf-8")
    print("\n".join(L[:len(ok) + 12]))


if __name__ == "__main__":
    main(*sys.argv[1:])
