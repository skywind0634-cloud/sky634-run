"""組み合わせ馬券（3連複・ワイド）を「当たる確率×オッズ」で選ぶ検証（2026-10-18）.
- 市場の3着内確率: JRA 最終オッズの単勝・複勝（odds/<YYYYMM>.json.gz, tools/backfill_jra_odds.py）から。
- こちらの3着内確率: 市場の確率＋フラグの○◎数・×▽▼数（data/cache/flag_backtest_rows.json）のロジスティック回帰。2022-23 で学習。
- 馬ごとの上乗せ＝こちら÷市場。組み合わせの期待値の比＝上乗せの積（市場オッズは組み合わせの確率を含んでいる前提）。
- 比が閾値以上・オッズが範囲内の組を、1レース最大 n 点買う。2024 / 2025-26（学習に使っていない期間）で回収率を出す。
使い方: python3 tools/combo_value.py → docs/analysis/combo_value.md
"""
import gzip, itertools, json, math, sqlite3
from collections import defaultdict
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
ODDS = ROOT / "data" / "cache" / "odds"


def norm(c):
    return "-".join(sorted([str(x) for x in c if str(x).isdigit()], key=int))


def load():
    c = sqlite3.connect(ROOT / "data" / "keiba.db")
    date = dict(c.execute("select race_id, date from races"))
    pay = {rid: json.loads(p) if p else {} for rid, p in c.execute("select race_id, payouts from races where date >= '2022-01-01'")}
    fin = defaultdict(dict); popnum = {}
    for rid, num, f, pop in c.execute("select race_id, number, finish, popularity from results r join races using(race_id) where date >= '2022-01-01'"):
        fin[rid][num] = f
        if pop:
            popnum[(rid, pop)] = num
    flags = {}
    for r in json.load(open(ROOT / "data" / "cache" / "flag_backtest_rows.json")):
        n = popnum.get((r["rid"], r["pop"]))
        if n:
            flags[(r["rid"], n)] = (r["plus"], r["minus"])
    races = []
    for f in sorted(ODDS.glob("*.json.gz")):
        with gzip.open(f, "rt", encoding="utf-8") as g:
            for rid, rec in json.load(g).items():
                tp = rec.get("tanpuku") or {}
                if rid not in fin or len(tp) < 8 or not rec.get("trio"):
                    continue
                hs = []
                for n, v in tp.items():
                    n = int(n)
                    if not v[0] or not v[1] or fin[rid].get(n) is None:
                        continue
                    pl, mi = flags.get((rid, n), (0, 0))
                    hs.append(dict(num=n, win=v[0], plc=(v[1] + (v[2] or v[1])) / 2, fin=fin[rid][n], plus=pl, minus=mi))
                if len(hs) < 8:
                    continue
                P = {k: {norm(str(a).replace("－", "-").split("-")): y for a, y in v} for k, v in pay.get(rid, {}).items()}
                races.append(dict(rid=rid, date=date.get(rid, ""), hs=hs, trio=rec["trio"], wide=rec.get("wide") or {}, P=P))
    return races


def feats(h, n):
    lw, lp = math.log(h["win"]), math.log(h["plc"])
    return [1.0, lw, lp, lw * lw, math.log(n)], [min(h["plus"], 6), min(h["minus"], 6),
                                                   min(h["plus"], 6) * (lw > math.log(15)), min(h["minus"], 6) * (lw > math.log(15))]


def fit(X, y, l2=1e-3, it=30):
    w = np.zeros(X.shape[1])
    for _ in range(it):
        p = 1 / (1 + np.exp(-X @ w))
        g = X.T @ (p - y) + l2 * w
        H = (X * (p * (1 - p))[:, None]).T @ X + l2 * np.eye(len(w))
        w -= np.linalg.solve(H, g)
    return w


def main():
    races = load()
    per = lambda d: "学習2022-23" if d < "2024-01-01" else "2024" if d < "2025-01-01" else "2025-26"  # noqa: E731
    tr = [r for r in races if per(r["date"]) == "学習2022-23"]
    Xa, Xb, y = [], [], []
    for r in tr:
        for h in r["hs"]:
            a, b = feats(h, len(r["hs"]))
            Xa.append(a); Xb.append(a + b); y.append(1.0 if h["fin"] <= 3 else 0.0)
    Xa, Xb, y = np.array(Xa), np.array(Xb), np.array(y)
    wa, wb = fit(Xa, y), fit(Xb, y)
    L = ["# 組み合わせ馬券を期待値で選ぶ（自動生成 tools/combo_value.py）", "",
         f"- レース数: 学習 {len(tr)} / 2024 {sum(per(r['date']) == '2024' for r in races)} / 2025-26 {sum(per(r['date']) == '2025-26' for r in races)}",
         f"- 学習の重み（フラグ部分）: ○◎数 {wb[5]:+.3f}・×▽▼数 {wb[6]:+.3f}・○◎×単勝15倍超 {wb[7]:+.3f}・×▽▼×15倍超 {wb[8]:+.3f}", ""]
    for r in races:
        n = len(r["hs"])
        for h in r["hs"]:
            a, b = feats(h, n)
            pa = 1 / (1 + math.exp(-np.dot(wa, a))); pb = 1 / (1 + math.exp(-np.dot(wb, a + b)))
            h["lift"] = pb / pa
    res = defaultdict(lambda: defaultdict(lambda: [0, 0, 0, 0, 0]))
    specs = []
    for th in (1.2, 1.3, 1.4, 1.5, 1.7):
        for lo, hi in ((50, 300), (100, 1000), (200, 3000), (300, 10000)):
            for nmax in (3, 5, 10):
                specs.append(("3連複", th, lo, hi, nmax))
        for lo, hi in ((10, 50), (20, 100), (30, 300)):
            for nmax in (3, 5):
                specs.append(("ワイド", th, lo, hi, nmax))
    for r in races:
        pr = per(r["date"])
        lift = {h["num"]: h["lift"] for h in r["hs"]}
        for kind, th, lo, hi, nmax in specs:
            book = r["trio"] if kind == "3連複" else r["wide"]
            cand = []
            for k, o in book.items():
                o = o if not isinstance(o, list) else o[0]
                if not o or not (lo <= o <= hi):
                    continue
                ns = [int(x) for x in k.split("-")]
                if any(x not in lift for x in ns):
                    continue
                s = math.prod(lift[x] for x in ns)
                if s >= th:
                    cand.append((s, k))
            cand = sorted(cand, reverse=True)[:nmax]
            if not cand:
                continue
            rets = [r["P"].get(kind, {}).get(k, 0) for _, k in cand]
            a = res[(kind, th, lo, hi, nmax)][pr]
            a[0] += 1; a[1] += len(cand); a[2] += sum(rets) > 0; a[3] += sum(rets); a[4] += sum(1 for x in rets if x >= 100000)
    rows = []
    for key, d in res.items():
        A = [d[p] for p in ("学習2022-23", "2024", "2025-26")]
        if min(x[0] for x in A) < 30:
            continue
        roi = [x[3] / max(x[1] * 100, 1) * 100 for x in A]
        rows.append((min(roi[1:]), key, A, roi))
    rows.sort(reverse=True)
    L += ["| 券種 | 比の閾値 | オッズ範囲 | 最大点数 | レース数(学習/2024/25-26) | 点数/R | 的中率 | 回収率 | 10万円以上の的中 |", "|---|---|---|---|---|---|---|---|---|"]
    for mn, (kind, th, lo, hi, nmax), A, roi in rows[:40]:
        b = "**" if min(roi) > 100 else ""
        L.append(f"| {kind} | {th} | {lo}〜{hi}倍 | {nmax} | " + "/".join(str(x[0]) for x in A) + f" | {sum(x[1] for x in A) / sum(x[0] for x in A):.1f} | "
                 + "/".join(f"{x[2] / x[0] * 100:.1f}%" for x in A) + " | " + b + "/".join(f"{r:.0f}%" for r in roi) + b + " | " + "/".join(str(x[4]) for x in A) + " |")
    (ROOT / "docs" / "analysis" / "combo_value.md").write_text("\n".join(L) + "\n", encoding="utf-8")
    json.dump({"wa": wa.tolist(), "wb": wb.tolist()}, open(ROOT / "data" / "knowledge" / "combo_value_model.json", "w"))
    print("\n".join(L))


if __name__ == "__main__":
    main()
