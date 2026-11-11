"""近走成績・騎手・厩舎・血統の成績を全部入れた3着内モデル（勾配ブースティング, 2026-10-24, ユーザー「もともとの精度上げろ」）.
特徴（すべてそのレースより前のデータだけ）: 単勝オッズ・人気・頭数・枠・斤量・年齢・性・馬体重と増減、
近5走（着順率・タイム差・上がり順位率・1角の位置率・人気）、前走からの間隔・距離の増減・芝ダの替わり、
騎手・調教師・父（芝ダ別）の3着内の実数÷人気からの見込み（累積）、同コースの成績。
学習 2021-23・選定 2024・テスト 2025-26。市場だけのモデルと、対数損失・レースごとの上位3頭の3着内率・上乗せの大きい馬の回収率で比べる。
使い方: python3 tools/form_model.py → docs/analysis/form_model.md
"""
import json, math, sqlite3, sys
from collections import defaultdict
from datetime import date
from pathlib import Path
import numpy as np
from sklearn.ensemble import HistGradientBoostingClassifier
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import log_loss

ROOT = Path(__file__).resolve().parents[1]
NAN = float("nan")


def per(d):
    return "train" if d < "2024-01-01" else "valid" if d < "2025-01-01" else "test"


def build():
    c = sqlite3.connect(ROOT / "data" / "keiba.db")
    races = {r[0]: r[1:] for r in c.execute("select race_id,date,course,surface,distance,going,n_runners,race_no,grade,payouts from races")}
    res = defaultdict(list)
    for r in c.execute("select r.race_id,r.horse_id,r.finish,r.gate,r.number,r.sex,r.age,r.weight_carried,r.jockey,r.trainer,r.time_sec,"
                       "r.passing,r.last3f,r.odds,r.popularity,r.body_weight,r.body_weight_diff,h.sire from results r left join horses h using(horse_id)"):
        res[r[0]].append(r)
    base = defaultdict(lambda: [0, 0])
    for rs in res.values():
        for r in rs:
            if r[2] and r[14]:
                b = base[min(r[14], 16)]; b[0] += 1; b[1] += r[2] <= 3
    pe = {k: v[1] / v[0] for k, v in base.items()}
    hist = defaultdict(list)          # horse → [(date, fin_ratio, behind, l3rank_ratio, pos1_ratio, pop, dist, surface, course, top3)]
    cum = defaultdict(lambda: [0, 0.0, 0])  # key → [top3, expected, runs]
    X, meta = [], []
    order = sorted(res, key=lambda rid: (races[rid][0], rid) if rid in races else ("9", rid))
    by_date = defaultdict(list)
    for rid in order:
        if rid in races:
            by_date[races[rid][0]].append(rid)
    for d in sorted(by_date):
        dd = date.fromisoformat(d)
        updates = []
        for rid in by_date[d]:
            dt_, co, su, dist, going, n, rno, grade, pay = races[rid]
            rs = [r for r in res[rid] if r[2]]
            if len(rs) < 5 or su not in ("芝", "ダ"):
                continue
            n = len(rs)
            win = min((r[10] for r in rs if r[2] == 1 and r[10]), default=None)
            l3 = sorted(r[12] for r in rs if r[12])
            p = json.loads(pay) if pay else {}
            fk = {a: y for a, y in p.get("複勝", [])}; tk = {a: y for a, y in p.get("単勝", [])}
            for r in rs:
                _, hid, fin, gate, num, sex, age, wc, jk, tr, ts, pas, l3f, odds, pop, bw, bwd, sire = r
                h = hist[hid][-5:]
                def avg(i, k=5):
                    v = [x[i] for x in h[-k:] if x[i] == x[i]]
                    return sum(v) / len(v) if v else NAN
                last = h[-1] if h else None
                def ae(key):
                    a = cum[key]; return ((a[0] + 2) / (a[1] + 2), a[2])
                jae, jn = ae(("j", jk)); tae, tn = ae(("t", tr)); sae, sn = ae(("s", sire, su)); cae, cn = ae(("hc", hid, co, su))
                f = [math.log(odds) if odds else NAN, pop or NAN, n, (gate or 0) / 8, wc or NAN, age or NAN, 1.0 if str(sex).startswith("牝") else 0.0,
                     bw or NAN, bwd if bwd is not None else NAN, len(hist[hid]),
                     last[1] if last else NAN, avg(1, 3), min((x[1] for x in h), default=NAN), last[2] if last else NAN, avg(2, 3),
                     last[3] if last else NAN, avg(3, 3), last[4] if last else NAN, avg(4, 3), last[5] if last else NAN,
                     (dd - date.fromisoformat(last[0])).days if last else NAN, (dist - last[6]) if last and last[6] else NAN,
                     (1.0 if last[7] == su else 0.0) if last else NAN, sum(x[9] for x in h) / len(h) if h else NAN,
                     jae, math.log1p(jn), tae, math.log1p(tn), sae, math.log1p(sn), cae, cn, 1.0 if su == "芝" else 0.0, dist,
                     0.0 if (going or "良").startswith("良") else 1.0]
                X.append(f)
                meta.append((d, rid, num, pop, odds, fin, fk.get(str(num), 0), tk.get(str(num), 0)))
                try:
                    pos1 = int(str(pas).split("-")[0]) / n
                except (ValueError, TypeError):
                    pos1 = NAN
                updates.append((hid, jk, tr, sire, su, co, (d, fin / n, (ts - win) if ts and win else NAN,
                                (l3.index(l3f) + 1) / n if l3f in l3 else NAN, pos1, pop or NAN, dist, su, co, fin <= 3), fin <= 3, pe.get(min(pop or 16, 16), 0.2)))
        for hid, jk, tr, sire, su, co, rec, top, e in updates:
            hist[hid].append(rec)
            for key in (("j", jk), ("t", tr), ("s", sire, su), ("hc", hid, co, su)):
                a = cum[key]; a[0] += top; a[1] += e; a[2] += 1
    return np.array(X, dtype=float), meta


def main():
    X, meta = build()
    ok = ~np.isnan(X[:, 0])
    X = X[ok]; meta = [m for m, k in zip(meta, ok) if k]
    y = np.array([m[5] <= 3 for m in meta])
    sp = np.array([per(m[0]) for m in meta])
    S = {s: sp == s for s in ("train", "valid", "test")}
    mk = np.column_stack([X[:, 0], X[:, 0] ** 2, np.log(X[:, 2])])
    lr = LogisticRegression(max_iter=1000).fit(mk[S["train"]], y[S["train"]])
    pm = lr.predict_proba(mk)[:, 1]
    best = None
    for lr_, it in ((0.05, 300), (0.05, 600), (0.03, 800)):
        g = HistGradientBoostingClassifier(learning_rate=lr_, max_iter=it, max_leaf_nodes=31, min_samples_leaf=200, l2_regularization=1.0).fit(X[S["train"]], y[S["train"]])
        ll = log_loss(y[S["valid"]], g.predict_proba(X[S["valid"]])[:, 1])
        if best is None or ll < best[0]:
            best = (ll, (lr_, it), g)
    pg = best[2].predict_proba(X)[:, 1]
    L = ["# 近走成績・騎手・厩舎・血統の成績を入れた3着内モデル（tools/form_model.py）", "",
         f"- 学習 2021-23（{S['train'].sum()}頭）・選定 2024（{S['valid'].sum()}頭）・テスト 2025-26（{S['test'].sum()}頭）。設定 {best[1]}", "",
         "| 指標 | 市場だけ 2024 | モデル 2024 | 市場だけ 2025-26 | モデル 2025-26 |", "|---|---|---|---|---|"]
    def top3(mask, sc):
        g = defaultdict(list)
        for m, s_ in zip([m for m, k in zip(meta, mask) if k], sc[mask]):
            g[m[1]].append((s_, m[5] <= 3))
        tot = hit = 0
        for v in g.values():
            v.sort(key=lambda x: -x[0]); tot += 3; hit += sum(h for _, h in v[:3])
        return hit / tot
    L.append(f"| 対数損失 | {log_loss(y[S['valid']], pm[S['valid']]):.5f} | {log_loss(y[S['valid']], pg[S['valid']]):.5f} | "
             f"{log_loss(y[S['test']], pm[S['test']]):.5f} | {log_loss(y[S['test']], pg[S['test']]):.5f} |")
    L.append(f"| 上位3頭の3着内率 | {top3(S['valid'], pm):.1%} | {top3(S['valid'], pg):.1%} | {top3(S['test'], pm):.1%} | {top3(S['test'], pg):.1%} |")
    L += ["", "## 上乗せ（モデル÷市場）が大きい馬を買ったとき（複勝・単勝の回収率）", "", "| 上乗せ | 人気 | 2024 | 2025-26 |", "|---|---|---|---|"]
    for th in (1.1, 1.2, 1.3, 1.5):
        for pb, (a, b) in (("1-3番人気", (1, 3)), ("4-9番人気", (4, 9)), ("10番人気以下", (10, 99))):
            cells = []
            for s in ("valid", "test"):
                idx = [i for i in np.where(S[s])[0] if pg[i] / pm[i] >= th and a <= (meta[i][3] or 99) <= b]
                n = len(idx)
                cells.append(f"{n}頭・3着内{sum(meta[i][5] <= 3 for i in idx) / max(n, 1):.0%}・複{sum(meta[i][6] for i in idx) / max(n, 1):.0f}%・単{sum(meta[i][7] for i in idx) / max(n, 1):.0f}%")
            L.append(f"| {th} | {pb} | " + " | ".join(cells) + " |")
    (ROOT / "docs" / "analysis" / "form_model.md").write_text("\n".join(L) + "\n", encoding="utf-8")
    np.save(ROOT / "data" / "cache" / "form_pred.npy", np.column_stack([pm, pg]))
    json.dump(meta, open(ROOT / "data" / "cache" / "form_meta.json", "w"))
    print("\n".join(L))


if __name__ == "__main__":
    main()
