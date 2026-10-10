"""荒れたレース（3連単1万円以上・3連複3000円以上・馬連5000円以上）から逆算する分析.

1. どんなレースが荒れやすいか（レース条件別の発生率。発見〜2022 / 確認 2023-24 / テスト 2025〜 で安定しているか）
2. 荒れたレースで3着内に来た人気薄（7番人気以下）はどんな馬か（全人気薄と比べた特徴）
3. その特徴を持つ人気薄を全レースで買ったら回収率は100%を超えるか（単勝・複勝, 3期間すべてで）
4. 荒れやすい条件のレースだけで、人気薄の組み合わせ馬券（ワイド・馬連・三連複）を買ったら回収率は100%を超えるか

出力: docs/analysis/upsets.md
"""
from __future__ import annotations

import json
import sys
from collections import defaultdict
from itertools import combinations
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from keiba import db, value as V   # noqa: E402

PERIODS = ("発見", "確認", "テスト")


def pay_of(p, key, combo=None):
    out = []
    for c, y in p.get(key, []):
        nums = sorted(int(x) for x in str(c).replace("→", "-").split("-") if x.strip().isdigit())
        if combo is None or nums == sorted(combo):
            out.append(y or 0)
    return out


def load():
    conn = db.connect()
    rows = V.load(conn)
    races = {}
    for r in conn.execute("SELECT race_id, payouts FROM races"):
        try:
            races[r[0]] = json.loads(r[1] or "{}")
        except ValueError:
            races[r[0]] = {}
    # 前走の情報（馬ごと・日付順）
    by_h = defaultdict(list)
    for r in rows:
        by_h[r["horse_id"]].append(r)
    for lst in by_h.values():
        lst.sort(key=lambda r: r["date"])
        prev = None
        for r in lst:
            r["prev_fin"] = prev["finish"] if prev else None
            r["prev_pop"] = prev["popularity"] if prev else None
            r["prev_jockey"] = prev["jockey"] if prev else None
            r["prev_grade"] = prev["grade"] if prev else None
            r["prev_wt"] = prev["weight_carried"] if prev else None
            r["prev_nr"] = prev["n_runners"] if prev else None
            prev = r
    by_r = defaultdict(list)
    for r in rows:
        by_r[r["race_id"]].append(r)
    return by_r, races


def upset_flags(p):
    t = max(pay_of(p, "3連単") or [0])
    f = max(pay_of(p, "3連複") or [0])
    u = max(pay_of(p, "馬連") or [0])
    return {"3連単1万↑": t >= 10000, "3連複3000↑": f >= 3000, "馬連5000↑": u >= 5000,
            "いずれか": t >= 10000 or f >= 3000 or u >= 5000}


# ---------------------------------------------------------------- 特徴量（レース前に分かるもの）
def b_fin(x):
    return None if not x else ("前走1-3着" if x <= 3 else "前走4-9着" if x <= 9 else "前走10着↓")


def b_pop(x):
    return None if not x else ("前走1-3人気" if x <= 3 else "前走4-9人気" if x <= 9 else "前走10人気↓")


GRADE_RANK = {"G1": 7, "G2": 6, "G3": 5, "L": 4, "OP": 4, "3勝": 3, "2勝": 2, "1勝": 1, "新馬": 0, "未勝利": 0}


def class_chg(r):
    a, b = GRADE_RANK.get(r.get("prev_grade") or ""), GRADE_RANK.get(r.get("grade") or "")
    if a is None or b is None:
        return None
    return "昇級" if b > a else "降級" if b < a else "同クラス"


HORSE_F = {
    "人気": lambda r: str(r["popularity"]) + "番人気" if r["popularity"] and r["popularity"] <= 12 else "13番人気↓",
    "枠": lambda r: V.gate_group(r["gate"]),
    "前走脚質": lambda r: r["prev_style"],
    "前走着順": lambda r: b_fin(r["prev_fin"]),
    "前走人気": lambda r: b_pop(r["prev_pop"]),
    "前走 人気より上の着順": lambda r: None if not (r["prev_fin"] and r["prev_pop"]) else
    ("前走 人気より5着以上良い" if r["prev_pop"] - r["prev_fin"] >= 5 else
     "前走 人気より5着以上悪い" if r["prev_fin"] - r["prev_pop"] >= 5 else "前走 人気並み"),
    "クラス": class_chg,
    "距離変化": lambda r: r["dchg"],
    "ローテ": lambda r: r["interval"],
    "乗り替わり": lambda r: None if not r["prev_jockey"] else ("乗り替わり" if r["prev_jockey"] != r["jockey"] else "継続騎乗"),
    "斤量変化": lambda r: None if not (r["prev_wt"] and r["weight_carried"]) else
    ("斤量減" if r["weight_carried"] < r["prev_wt"] - 0.9 else "斤量増" if r["weight_carried"] > r["prev_wt"] + 0.9 else "斤量同"),
    "馬体重増減": lambda r: None if r["body_weight_diff"] is None else
    ("-10kg以上" if r["body_weight_diff"] <= -10 else "+10kg以上" if r["body_weight_diff"] >= 10 else "±8kg以内"),
    "性齢": lambda r: f"{r['sex']}{min(r['age'] or 0, 6)}歳{'↑' if (r['age'] or 0) >= 6 else ''}",
    "父系統": lambda r: r["sire_line"],
    "母父系統": lambda r: r["damsire_line"],
    "国別(父)": lambda r: _ct(r["sire_line"]),
    "騎手": lambda r: r["jockey"],
    "調教師": lambda r: r["trainer"],
}


def _ct(line):
    from keiba import knowledge as K
    try:
        return K.country_type(line)
    except Exception:   # noqa: BLE001
        return None


RACE_F = {
    "競馬場": lambda r: r["course"],
    "芝ダ": lambda r: r["surface"],
    "距離帯": lambda r: f"{r['surface']}{r['band']}",
    "コース": lambda r: f"{r['course']}{r['surface']}{r['distance']}",
    "馬場": lambda r: r["going"],
    "クラス": lambda r: r["grade"] or "条件",
    "頭数": lambda r: "〜10頭" if r["n_runners"] <= 10 else "11-14頭" if r["n_runners"] <= 14 else "15頭〜",
    "季節": lambda r: r["season"],
    "レース番号": lambda r: f"{r['race_no']}R",
    "直線": lambda r: f"{r['surface']}直線{r['straight_cat']}",
    "坂": lambda r: f"{r['surface']}{r['slope']}",
    "ハンデ": lambda r: "ハンデ" if "ハンデ" in (r.get("race_name") or "") else None,
    "牝馬限定": lambda r: "牝馬限定" if "牝" in (r.get("race_name") or "") else None,
}


def pct(a, b):
    return f"{a / b:.0%}" if b else "-"


def main(flag="3連複3000↑", topn=3, min_pop=7, out_name="upsets.md"):
    by_r, races = load()
    L = ["# 荒れたレースからの逆算分析（自動生成, tools/upset_analysis.py）", "",
         "- 荒れたレース = 3連単1万円以上・3連複3000円以上・馬連5000円以上。人気・枠・前走など、すべてレース前に分かる情報で分類。",
         "- 期間: 発見 〜2022 / 確認 2023-24 / テスト 2025〜。3期間とも同じ向きの傾向だけを『使える』とみなす。",
         "- 回収率は実際の払戻。人気は確定人気（前売りとはずれる）。", ""]
    # ---------------- 1. 発生率
    tot = defaultdict(lambda: defaultdict(int))
    meta = {}
    for rid, hs in by_r.items():
        p = races.get(rid) or {}
        if not p.get("3連単") and not p.get("3連複"):
            continue
        r0 = hs[0]
        meta[rid] = (r0, upset_flags(p))
        per = r0["period"]
        for k, v in upset_flags(p).items():
            tot[per][k] += v
        tot[per]["n"] += 1
    L += ["## 1. 荒れたレースの割合", "", "| 期間 | レース | 3連単1万↑ | 3連複3000↑ | 馬連5000↑ | いずれか |", "|---|--:|--:|--:|--:|--:|"]
    for per in PERIODS:
        t = tot[per]
        L.append(f"| {per} | {t['n']} | {pct(t['3連単1万↑'], t['n'])} | {pct(t['3連複3000↑'], t['n'])} | "
                 f"{pct(t['馬連5000↑'], t['n'])} | {pct(t['いずれか'], t['n'])} |")
    L.append("")
    # ---------------- 2. レース条件別の荒れ率
    L += [f"## 2. 荒れやすいレース条件（{flag}の割合。3期間とも全体より高い/低いものに印）", ""]
    stable_races = {}
    for fname, f in RACE_F.items():
        acc = defaultdict(lambda: defaultdict(lambda: [0, 0]))
        for rid, (r0, fl) in meta.items():
            try:
                k = f(r0)
            except (KeyError, TypeError):
                continue
            if k is None:
                continue
            a = acc[k][r0["period"]]
            a[0] += 1
            a[1] += fl[flag]
        lines = []
        for k, d in acc.items():
            ns = [d[p][0] for p in PERIODS]
            if min(ns) < (30 if fname != "コース" else 25):
                continue
            rates = [d[p][1] / d[p][0] for p in PERIODS]
            base = [tot[p][flag] / tot[p]["n"] for p in PERIODS]
            up = all(x > b * 1.1 for x, b in zip(rates, base))
            down = all(x < b * 0.9 for x, b in zip(rates, base))
            if fname in ("コース",) and not (up or down):
                continue
            mark = "荒れやすい" if up else "堅い" if down else ""
            if up:
                stable_races[(fname, k)] = rates
            lines.append((-(sum(rates) / 3), f"| {k} | {' / '.join(str(n) for n in ns)} | "
                                              f"{' / '.join(f'{x:.0%}' for x in rates)} | {mark} |"))
        if not lines:
            continue
        L += [f"### {fname}", "", f"| 条件 | レース数(発見/確認/テスト) | {flag}の割合 | 判定 |", "|---|--:|--:|---|"]
        L += [s for _, s in sorted(lines)[:25]]
        L.append("")
    # ---------------- 3. 荒れたレースで来た人気薄の特徴
    L += [f"## 3. 人気薄（{min_pop}番人気以下）で{topn}着内に来やすい特徴", "",
          f"全レースの{min_pop}番人気以下と比べて、{topn}着内に来た割合が3期間とも高い/低い特徴。回収率も併記。", ""]
    cand = []
    for fname, f in HORSE_F.items():
        acc = defaultdict(lambda: defaultdict(lambda: [0, 0, 0, 0]))   # 走, 3着内, 単払戻, 複払戻
        base = defaultdict(lambda: [0, 0, 0, 0])
        for rid, hs in by_r.items():
            for r in hs:
                if not r["popularity"] or r["popularity"] < min_pop or not r["finish"]:
                    continue
                try:
                    k = f(r)
                except (KeyError, TypeError):
                    continue
                for a in (acc[k][r["period"]], base[r["period"]]) if k is not None else (base[r["period"]],):
                    a[0] += 1
                    a[1] += r["finish"] <= topn
                    a[2] += r["win_pay"] or 0
                    a[3] += r["place_pay"] or 0
        rows = []
        for k, d in acc.items():
            ns = [d[p][0] for p in PERIODS]
            if min(ns) < (150 if fname in ("騎手", "調教師") else 300):
                continue
            t3 = [d[p][1] / d[p][0] for p in PERIODS]
            bt = [base[p][1] / base[p][0] for p in PERIODS]
            wr = [d[p][2] / d[p][0] for p in PERIODS]
            pr = [d[p][3] / d[p][0] for p in PERIODS]
            lift = [a / b for a, b in zip(t3, bt)]
            if all(x >= 1.15 for x in lift) or all(x <= 0.85 for x in lift):
                rows.append((-(sum(lift)), fname, k, ns, t3, lift, wr, pr))
                cand.append((fname, k, ns, t3, lift, wr, pr))
        if rows:
            L += [f"### {fname}", "", f"| 特徴 | 頭数(発見/確認/テスト) | {topn}着内率 | 人気薄全体比 | 単回収 | 複回収 |",
                  "|---|--:|--:|--:|--:|--:|"]
            for _, _, k, ns, t3, lift, wr, pr in sorted(rows)[:20]:
                L.append(f"| {k} | {'/'.join(map(str, ns))} | {' / '.join(f'{x:.1%}' for x in t3)} | "
                         f"{' / '.join(f'{x:.2f}' for x in lift)} | {' / '.join(f'{x:.0f}%' for x in wr)} | "
                         f"{' / '.join(f'{x:.0f}%' for x in pr)} |")
            L.append("")
    # ---------------- 4. 回収率100%超（3期間すべて）
    L += ["## 4. 3期間すべてで回収率100%を超えた人気薄の特徴（単勝・複勝）", ""]
    hit = [(f, k, ns, wr, pr) for f, k, ns, t3, lift, wr, pr in cand if min(wr) >= 100 or min(pr) >= 100]
    if hit:
        L += ["| 特徴 | 頭数 | 単回収 | 複回収 |", "|---|--:|--:|--:|"]
        for f, k, ns, wr, pr in hit:
            L.append(f"| {f}: {k} | {'/'.join(map(str, ns))} | {' / '.join(f'{x:.0f}%' for x in wr)} | "
                     f"{' / '.join(f'{x:.0f}%' for x in pr)} |")
    else:
        L.append("- 該当なし（特徴1つだけで3期間とも100%を超えるものは無い）")
    L.append("")
    # 2つの特徴の組み合わせ（発見で選び、確認・テストで確かめる）
    L += ["### 特徴2つの組み合わせ（発見期間で単勝または複勝回収率120%以上・200頭以上を選び、確認・テストで検証）", ""]
    keys = [k for k in HORSE_F if k not in ("騎手", "調教師")]
    acc2 = defaultdict(lambda: defaultdict(lambda: [0, 0, 0, 0]))
    for rid, hs in by_r.items():
        for r in hs:
            if not r["popularity"] or r["popularity"] < min_pop or not r["finish"]:
                continue
            vals = {}
            for fn in keys:
                try:
                    vals[fn] = HORSE_F[fn](r)
                except (KeyError, TypeError):
                    vals[fn] = None
            for a, b in combinations(keys, 2):
                if vals[a] is None or vals[b] is None:
                    continue
                x = acc2[(a, vals[a], b, vals[b])][r["period"]]
                x[0] += 1
                x[1] += r["finish"] <= topn
                x[2] += r["win_pay"] or 0
                x[3] += r["place_pay"] or 0
    found = []
    for key, d in acc2.items():
        dv = d["発見"]
        if dv[0] < 200:
            continue
        if dv[2] / dv[0] >= 120 or dv[3] / dv[0] >= 120:
            c, t = d["確認"], d["テスト"]
            if c[0] < 80 or t[0] < 50:
                continue
            found.append((key, [d[p] for p in PERIODS]))
    ok = [(k, ds) for k, ds in found
          if all(x[2] / x[0] >= 100 for x in ds) or all(x[3] / x[0] >= 100 for x in ds)]
    L.append(f"- 発見期間で選ばれた組み合わせ {len(found)} 件のうち、確認・テストでも100%超を保ったもの {len(ok)} 件")
    if ok:
        L += ["", f"| 組み合わせ | 頭数(発見/確認/テスト) | 単回収 | 複回収 | {topn}着内率 |", "|---|--:|--:|--:|--:|"]
        for (a, va, b, vb), ds in sorted(ok, key=lambda x: -sum(y[0] for y in x[1]))[:30]:
            L.append(f"| {a}={va} × {b}={vb} | {'/'.join(str(x[0]) for x in ds)} | "
                     f"{' / '.join(f'{x[2] / x[0]:.0f}%' for x in ds)} | {' / '.join(f'{x[3] / x[0]:.0f}%' for x in ds)} | "
                     f"{' / '.join(f'{x[1] / x[0]:.0%}' for x in ds)} |")
    L.append("")
    # ---------------- 5. 荒れやすいレースで人気薄の組み合わせ馬券
    L += ["## 5. 組み合わせ馬券の回収率（全レース / 荒れやすい条件のレースだけ）", "",
          f"荒れやすい条件 = 2章で3期間とも{flag}の割合が全体の1.1倍超だった条件（競馬場・距離帯・頭数など）に1つ以上当てはまるレース。", ""]

    def is_rough(r0):
        for (fname, k) in stable_races:
            try:
                if RACE_F[fname](r0) == k:
                    return True
            except (KeyError, TypeError):
                pass
        return False

    def tickets(hs, plan):
        pop = {r["popularity"]: r["number"] for r in hs if r["popularity"]}
        sel = lambda a, b: [pop[i] for i in range(a, b + 1) if i in pop]
        if plan == "ワイドBOX 4-7番人気":
            return [("ワイド", c) for c in combinations(sel(4, 7), 2)]
        if plan == "馬連BOX 4-7番人気":
            return [("馬連", c) for c in combinations(sel(4, 7), 2)]
        if plan == "三連複BOX 4-8番人気":
            return [("3連複", c) for c in combinations(sel(4, 8), 3)]
        if plan == "三連複 1番人気-4〜8番人気":
            return [("3連複", (pop[1], *c)) for c in combinations(sel(4, 8), 2)] if 1 in pop else []
        if plan == "三連複 2番人気軸-3〜8番人気":
            return [("3連複", (pop[2], *c)) for c in combinations(sel(3, 7), 2)] if 2 in pop else []
        if plan == "馬連 1番人気-5〜10番人気":
            return [("馬連", (pop[1], x)) for x in sel(5, 10)] if 1 in pop else []
        if plan == "馬連 2番人気-5〜10番人気":
            return [("馬連", (pop[2], x)) for x in sel(5, 10)] if 2 in pop else []
        if plan == "馬連 1・2番人気-5〜9番人気":
            return [("馬連", (pop[a], x)) for a in (1, 2) if a in pop for x in sel(5, 9)]
        if plan == "馬連BOX 5-9番人気":
            return [("馬連", c) for c in combinations(sel(5, 9), 2)]
        if plan == "ワイド 1番人気-7〜12番人気":
            return [("ワイド", (pop[1], x)) for x in sel(7, 12)] if 1 in pop else []
        if plan == "複勝 7〜12番人気":
            return [("複勝", (x,)) for x in sel(7, 12)]
        if plan == "単勝 7〜12番人気":
            return [("単勝", (x,)) for x in sel(7, 12)]
        return []

    plans = ["馬連 1番人気-5〜10番人気", "馬連 2番人気-5〜10番人気", "馬連 1・2番人気-5〜9番人気", "馬連BOX 5-9番人気",
             "ワイドBOX 4-7番人気", "馬連BOX 4-7番人気", "三連複BOX 4-8番人気", "三連複 1番人気-4〜8番人気",
             "三連複 2番人気軸-3〜8番人気", "ワイド 1番人気-7〜12番人気", "複勝 7〜12番人気", "単勝 7〜12番人気"]
    L += ["| 買い方 | 対象 | 発見 | 確認 | テスト |", "|---|---|--:|--:|--:|"]
    for plan in plans:
        for scope in ("全レース", "荒れやすい条件"):
            res = []
            for per in PERIODS:
                cost = back = 0
                for rid, (r0, fl) in meta.items():
                    if r0["period"] != per or (scope != "全レース" and not is_rough(r0)):
                        continue
                    T = tickets(by_r[rid], plan)
                    p = races[rid]
                    cost += 100 * len(T)
                    back += sum(sum(pay_of(p, k, c)) for k, c in T)
                res.append(f"{back / cost:.0%}" if cost else "-")
            L.append(f"| {plan} | {scope} | {' | '.join(res)} |")
    L.append("")
    out = ROOT / "docs" / "analysis" / out_name
    out.write_text("\n".join(L) + "\n", encoding="utf-8")
    print(out)


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "umaren":
        main("馬連5000↑", topn=2, min_pop=5, out_name="upsets_umaren.md")
    else:
        main()
