"""短距離戦（1400m以下）・競馬場×距離別の、馬券になる傾向の探索.

- 対象を 芝/ダの距離帯・コース（競馬場×芝ダ×距離）・頭数で絞り、その中で
  人気帯 × 特徴（枠・前走脚質・距離変化・前走着順・人気落ち・父系統・国別タイプ・母父系統・騎手・調教師・斤量・馬体重・ローテ・性齢）
  の単勝・複勝回収率を見る。
- 偶然を避けるため: 発見期間（〜2022）で回収率120%以上・100頭以上を選び、確認（2023-24）・テスト（2025〜）で検証。
  さらに「最大払戻を除いた回収率」と「上位3本の払戻が占める割合」で、一発の高配当頼みかを確かめる。
出力: docs/analysis/sprint.md
"""
from __future__ import annotations

import sys
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tools"))

from upset_analysis import HORSE_F, PERIODS, load   # noqa: E402


def pop_band(p):
    return None if not p else "1-3番人気" if p <= 3 else "4-6番人気" if p <= 6 else "7-9番人気" if p <= 9 else "10番人気↓"


SUBSETS = {
    "芝1200以下": lambda r: r["surface"] == "芝" and r["distance"] <= 1200,
    "芝1400": lambda r: r["surface"] == "芝" and r["distance"] == 1400,
    "ダ1200以下": lambda r: r["surface"] == "ダ" and r["distance"] <= 1200,
    "ダ1300-1400": lambda r: r["surface"] == "ダ" and 1300 <= r["distance"] <= 1400,
    "短距離(1400以下)×15頭以上": lambda r: r["distance"] <= 1400 and r["n_runners"] >= 15,
    "短距離(1400以下)×14頭以下": lambda r: r["distance"] <= 1400 and r["n_runners"] <= 14,
    "マイル(1500-1700)": lambda r: 1500 <= r["distance"] <= 1700,
    "中距離(1800-2200)": lambda r: 1800 <= r["distance"] <= 2200,
    "長距離(2300以上)": lambda r: r["distance"] >= 2300,
}
FEATS = {k: v for k, v in HORSE_F.items() if k != "人気"}


class Acc:
    __slots__ = ("n", "t3", "w", "p", "wl", "pl")

    def __init__(self):
        self.n = self.t3 = self.w = self.p = 0
        self.wl, self.pl = [], []

    def add(self, r):
        self.n += 1
        self.t3 += (r["finish"] or 99) <= 3
        w, p = r["win_pay"] or 0, r["place_pay"] or 0
        self.w += w
        self.p += p
        if w:
            self.wl.append(w)
        if p:
            self.pl.append(p)


def scan(rows, subset_name, sub, extra_key=None):
    acc = defaultdict(lambda: defaultdict(Acc))
    for r in rows:
        if not r["finish"] or not r["popularity"] or not sub(r):
            continue
        pb = pop_band(r["popularity"])
        keys = [("人気帯のみ", "-")]
        for fn, f in FEATS.items():
            try:
                v = f(r)
            except (KeyError, TypeError):
                v = None
            if v is not None:
                keys.append((fn, v))
        if extra_key:
            keys = [(f"{extra_key(r)}", "-")] + [(f"{extra_key(r)}×{a}", b) for a, b in keys[1:]]
        for k in keys:
            acc[(k, pb)][r["period"]].add(r)
    return acc


def robust(a: Acc, kind: str) -> tuple[float, float]:
    tot = a.w if kind == "単" else a.p
    lst = sorted(a.wl if kind == "単" else a.pl, reverse=True)
    ex1 = (tot - (lst[0] if lst else 0)) / a.n
    top3 = sum(lst[:3]) / tot if tot else 0
    return ex1, top3


def main():
    by_r, _ = load()
    rows = [r for hs in by_r.values() for r in hs]
    L = ["# 短距離・距離帯・コース別の傾向探索（自動生成, tools/sprint_analysis.py）", "",
         "- 発見期間（〜2022）で単勝または複勝の回収率120%以上・100頭以上の条件を選び、確認（2023-24）・テスト（2025〜）で100%以上を保ったものだけを残す。",
         "- 『最大除く』= 一番大きい払戻1本を除いた回収率（確認＋テスト期間）。『上位3本』= 払戻のうち上位3本が占める割合。高いほど一発頼み。",
         "- 人気は確定人気。", ""]
    summary = []
    for name, sub in SUBSETS.items():
        acc = scan(rows, name, sub)
        tested = found = 0
        out = []
        for ((fn, v), pb), d in acc.items():
            dv = d["発見"]
            if dv.n < 100:
                continue
            for kind in ("単", "複"):
                tested += 1
                r0 = (dv.w if kind == "単" else dv.p) / dv.n
                if r0 < 120:
                    continue
                c, t = d["確認"], d["テスト"]
                if c.n < 50 or t.n < 30:
                    continue
                rc = (c.w if kind == "単" else c.p) / c.n
                rt = (t.w if kind == "単" else t.p) / t.n
                found += 1
                if rc >= 100 and rt >= 100:
                    m = Acc()
                    for x in (c, t):
                        m.n += x.n
                        m.w += x.w
                        m.p += x.p
                        m.wl += x.wl
                        m.pl += x.pl
                        m.t3 += x.t3
                    ex1, top3 = robust(m, kind)
                    out.append((fn, v, pb, kind, dv.n, c.n, t.n, r0, rc, rt, ex1, top3, m.t3 / m.n))
        summary.append((name, tested, found, len(out)))
        L += [f"## {name}", "", f"- 調べた条件 {tested} / 発見期間で120%以上 {found} / 確認・テストでも100%以上 {len(out)}", ""]
        if out:
            L += ["| 条件 | 人気帯 | 券種 | 頭数(発見/確認/テスト) | 回収率(発見/確認/テスト) | 最大除く | 上位3本 | 3着内率 |",
                  "|---|---|---|--:|--:|--:|--:|--:|"]
            for fn, v, pb, kind, n0, n1, n2, r0, rc, rt, ex1, top3, t3 in sorted(out, key=lambda x: -(x[5] + x[6]))[:30]:
                L.append(f"| {fn}={v} | {pb} | {kind} | {n0}/{n1}/{n2} | {r0:.0f}% / {rc:.0f}% / {rt:.0f}% | "
                         f"{ex1:.0f}% | {top3:.0%} | {t3:.0%} |")
        L.append("")
    # コース別（競馬場×芝ダ×距離）: 人気帯×枠・前走脚質・距離変化だけ
    L += ["## コース別（競馬場×芝ダ×距離, 人気帯×枠・前走脚質・距離変化・父の国別タイプ）", ""]
    keep = {"枠", "前走脚質", "距離変化", "国別(父)"}
    acc = defaultdict(lambda: defaultdict(Acc))
    for r in rows:
        if not r["finish"] or not r["popularity"]:
            continue
        crs = f"{r['course']}{r['surface']}{r['distance']}"
        pb = pop_band(r["popularity"])
        for fn in keep:
            try:
                v = FEATS[fn](r)
            except (KeyError, TypeError):
                v = None
            if v is not None:
                acc[(crs, fn, v, pb)][r["period"]].add(r)
    out, tested, found = [], 0, 0
    for (crs, fn, v, pb), d in acc.items():
        dv = d["発見"]
        if dv.n < 60:
            continue
        for kind in ("単", "複"):
            tested += 1
            r0 = (dv.w if kind == "単" else dv.p) / dv.n
            if r0 < 120:
                continue
            c, t = d["確認"], d["テスト"]
            if c.n < 30 or t.n < 20:
                continue
            found += 1
            rc = (c.w if kind == "単" else c.p) / c.n
            rt = (t.w if kind == "単" else t.p) / t.n
            if rc >= 100 and rt >= 100:
                m = Acc()
                for x in (c, t):
                    m.n += x.n
                    m.w += x.w
                    m.p += x.p
                    m.wl += x.wl
                    m.pl += x.pl
                    m.t3 += x.t3
                ex1, top3 = robust(m, kind)
                out.append((crs, fn, v, pb, kind, dv.n, c.n, t.n, r0, rc, rt, ex1, top3, m.t3 / m.n))
    L += [f"- 調べた条件 {tested} / 発見期間で120%以上 {found} / 確認・テストでも100%以上 {len(out)}", "",
          "| コース | 条件 | 人気帯 | 券種 | 頭数 | 回収率(発見/確認/テスト) | 最大除く | 上位3本 | 3着内率 |",
          "|---|---|---|---|--:|--:|--:|--:|--:|"]
    for crs, fn, v, pb, kind, n0, n1, n2, r0, rc, rt, ex1, top3, t3 in sorted(out, key=lambda x: -(x[6] + x[7])):
        L.append(f"| {crs} | {fn}={v} | {pb} | {kind} | {n0}/{n1}/{n2} | {r0:.0f}% / {rc:.0f}% / {rt:.0f}% | "
                 f"{ex1:.0f}% | {top3:.0%} | {t3:.0%} |")
    L += ["", "## まとめ（条件の数と、生き残った数）", "", "| 対象 | 調べた条件 | 発見で120%以上 | 確認・テストも100%以上 |", "|---|--:|--:|--:|"]
    for name, a, b, c in summary + [("コース別", tested, found, len(out))]:
        L.append(f"| {name} | {a} | {b} | {c} |")
    (ROOT / "docs" / "analysis" / "sprint.md").write_text("\n".join(L) + "\n", encoding="utf-8")
    print("ok")


if __name__ == "__main__":
    main()
