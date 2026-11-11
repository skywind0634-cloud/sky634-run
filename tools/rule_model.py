"""材料ごとに重さを学んだ3着内確率モデル（2026-10-24, ユーザー「もともとの精度上げろ」）.
特徴: 市場（log単勝オッズ・その2乗・log頭数）＋材料（data/cache/rule_rows.json の各ルール、学習期間に200頭以上）。
学習 2021-23・選定 2024（正則化の強さ）・テスト 2025-26。比べるもの: 市場だけ / 市場＋フラグ点（○数・×数）/ 市場＋材料ごとの重さ。
評価: 対数損失、レースごとの上位3頭の3着内率（人気上位3頭との比較）、上乗せ（モデル÷市場）上位の複勝・単勝回収率。
注意: 材料の多くは2021-26年の全期間で「3期とも同じ向き」を条件に選ばれているので、テスト期間も完全な未来ではない。
使い方: python3 tools/rule_model.py → docs/analysis/rule_model.md, data/knowledge/rule_model.json
"""
import json, math, sys
from collections import Counter, defaultdict
from pathlib import Path
import numpy as np
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import log_loss

ROOT = Path(__file__).resolve().parents[1]


def per(d):
    return "train" if d < "2024-01-01" else "valid" if d < "2025-01-01" else "test"


def main():
    rows = [r for r in json.load(open(ROOT / "data" / "cache" / "rule_rows.json")) if r["odds"] and r["odds"] > 1 and r["fin"]]
    cnt = Counter(k for r in rows if per(r["date"]) == "train" for k, _ in r["rules"])
    keys = sorted(k for k, n in cnt.items() if n >= 200)
    ki = {k: i for i, k in enumerate(keys)}
    def X(r, mode):
        lo = math.log(r["odds"]); base = [lo, lo * lo, math.log(r["n"])]
        if mode == "market":
            return base
        if mode == "flag":
            p = sum(m in "◎○" for _, m in r["rules"]); m_ = sum(m in "×▽▼" for _, m in r["rules"])
            return base + [p, m_, p * (lo > math.log(15)), m_ * (lo > math.log(15))]
        v = [0.0] * (2 * len(keys))
        for k, _ in r["rules"]:
            if k in ki:
                v[ki[k]] = 1.0; v[len(keys) + ki[k]] = 1.0 * (lo > math.log(15))
        return base + v
    S = {s: [r for r in rows if per(r["date"]) == s] for s in ("train", "valid", "test")}
    y = {s: np.array([r["fin"] <= 3 for r in S[s]]) for s in S}
    res, models = {}, {}
    for mode in ("market", "flag", "rules"):
        Xs = {s: np.array([X(r, mode) for r in S[s]]) for s in S}
        best = None
        for C in ((1.0,) if mode != "rules" else (0.01, 0.03, 0.1, 0.3, 1.0)):
            m = LogisticRegression(C=C, max_iter=2000).fit(Xs["train"], y["train"])
            ll = log_loss(y["valid"], m.predict_proba(Xs["valid"])[:, 1])
            if best is None or ll < best[0]:
                best = (ll, C, m)
        m = best[2]; models[mode] = (m, best[1])
        res[mode] = {s: m.predict_proba(Xs[s])[:, 1] for s in S}
    L = ["# 材料ごとに重さを学んだ3着内モデル（tools/rule_model.py）", "",
         f"- 学習 2021-23（{len(S['train'])}頭）・選定 2024（{len(S['valid'])}頭）・テスト 2025-26（{len(S['test'])}頭）。材料 {len(keys)}種類（学習期間に200頭以上）。",
         "- 注意: 材料は2021-26年の全期間で一貫したものを選んでいるので、テストも完全な未来ではない。", "",
         "## 対数損失（小さいほど良い）", "", "| モデル | 2024 | 2025-26 |", "|---|---|---|"]
    for mode in res:
        L.append(f"| {mode} | {log_loss(y['valid'], res[mode]['valid']):.5f} | {log_loss(y['test'], res[mode]['test']):.5f} |")
    # レースごとの上位3頭の3着内率
    L += ["", "## レースごとに上位3頭を選んだときの3着内率（人気上位3頭と比べる）", "", "| 選び方 | 2024 | 2025-26 |", "|---|---|---|"]
    def top3(s, score):
        g = defaultdict(list)
        for r, sc in zip(S[s], score):
            g[r["rid"]].append((sc, r["fin"] <= 3))
        tot = hit = 0
        for v in g.values():
            v.sort(key=lambda x: -x[0]); tot += min(3, len(v)); hit += sum(h for _, h in v[:3])
        return hit / tot
    L.append(f"| 人気上位3頭 | {top3('valid', [-r['odds'] for r in S['valid']]):.1%} | {top3('test', [-r['odds'] for r in S['test']]):.1%} |")
    for mode in res:
        L.append(f"| {mode} | {top3('valid', res[mode]['valid']):.1%} | {top3('test', res[mode]['test']):.1%} |")
    # 上乗せの大きい馬の複勝・単勝回収
    L += ["", "## 上乗せ（rules÷market）が大きい馬を買ったとき", "", "| 上乗せ | 人気 | 2024 頭数・3着内率・複勝・単勝 | 2025-26 頭数・3着内率・複勝・単勝 |", "|---|---|---|---|"]
    for th in (1.15, 1.3, 1.5):
        for pb, (a, b) in (("4-9番人気", (4, 9)), ("10番人気以下", (10, 99)), ("全部", (1, 99))):
            cells = []
            for s in ("valid", "test"):
                sel = [r for r, p, q in zip(S[s], res["rules"][s], res["market"][s]) if p / q >= th and a <= r["pop"] <= b]
                n = len(sel)
                cells.append(f"{n}頭・{sum(r['fin'] <= 3 for r in sel) / max(n, 1):.0%}・{sum(r['fuku'] for r in sel) / max(n, 1):.0f}%・{sum(r['tan'] for r in sel) / max(n, 1):.0f}%")
            L.append(f"| {th} | {pb} | " + " | ".join(cells) + " |")
    m, C = models["rules"]
    w = m.coef_[0][3:3 + len(keys)]
    order = np.argsort(w)
    L += ["", f"## 重さの大きい材料（C={C}）", "", "| 材料 | 重さ | 学習頭数 |", "|---|---|---|"]
    for i in list(order[::-1][:25]) + list(order[:15]):
        L.append(f"| {keys[i]} | {w[i]:+.2f} | {cnt[keys[i]]} |")
    (ROOT / "docs" / "analysis" / "rule_model.md").write_text("\n".join(L) + "\n", encoding="utf-8")
    json.dump({"keys": keys, "coef": m.coef_[0].tolist(), "intercept": float(m.intercept_[0]),
               "market_coef": models["market"][0].coef_[0].tolist(), "market_intercept": float(models["market"][0].intercept_[0])},
              open(ROOT / "data" / "knowledge" / "rule_model.json", "w"), ensure_ascii=False)
    print("\n".join(L[:40]))


if __name__ == "__main__":
    main()
