"""高配当に絡む条件の総当たり探索（競馬場×距離×血統・騎手・調教師・枠・脚質・馬場など）と、偶然かどうかの検証.

やり方（すべて単勝・複勝の実際の払戻）:
 1. 角度ごとに「条件 × 人気帯」の組を全部作る（例: 父ロードカナロア × 中山芝1200 × 7〜9番人気）。
 2. 発見期間（〜2022）で回収率120%以上・一定頭数以上の組を選ぶ。
 3. 段階A: 発見だけで選んだ組をまとめて買ったら、確認（2023-24）・テスト（2025〜）で何%か（完全に未来のデータ）。
    段階B: 発見＋確認の両方で120%以上の組を選び、テスト（2025〜）で何%か。
 4. 偶然の基準: 馬をランダムに同じ大きさのグループに分けた「でたらめな条件」で同じ手順を行い、
    でたらめでも何件生き残るか・段階A/Bで何%になるかを比べる（これを上回らなければ偶然）。
出力: docs/analysis/angles.md
"""
from __future__ import annotations

import hashlib
import sys
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tools"))

from upset_analysis import load   # noqa: E402


from keiba.angles import ANGLES, pop_band as pb   # noqa: E402

NULL_K = 400   # でたらめな条件の数（馬IDのハッシュで割り振る）


def fake(r):
    h = int(hashlib.md5((r["horse_id"] + r["race_id"]).encode()).hexdigest()[:8], 16)
    return ("でたらめ", h % NULL_K)


class A:
    __slots__ = ("n", "w", "p", "t3", "ws", "ps")

    def __init__(self):
        self.n = self.w = self.p = self.t3 = 0
        self.ws, self.ps = [], []


def run_angle(rows, f, min_n):
    acc = defaultdict(lambda: defaultdict(A))
    for r in rows:
        if not r["finish"] or not r["popularity"]:
            continue
        try:
            k = f(r)
        except (KeyError, TypeError):
            continue
        if k is None or any(x is None for x in k):
            continue
        a = acc[(k, pb(r["popularity"]))][r["period"]]
        a.n += 1
        a.t3 += r["finish"] <= 3
        w, p = r["win_pay"] or 0, r["place_pay"] or 0
        a.w += w
        a.p += p
        if w:
            a.ws.append(w)
        if p:
            a.ps.append(p)
    res = {"cand": 0, "A": {}, "B": {}, "surv": []}
    for kind in ("単", "複"):
        pickA, pickB = [], []
        for key, d in acc.items():
            dv = d["発見"]
            if dv.n < min_n:
                continue
            res["cand"] += 1
            r0 = (dv.w if kind == "単" else dv.p) / dv.n
            if r0 >= 120:
                pickA.append(d)
                c = d["確認"]
                if c.n >= min_n // 2 and (c.w if kind == "単" else c.p) / c.n >= 120:
                    pickB.append((key, d))
        def roi(ds, per):
            n = sum(x[per].n for x in ds)
            s = sum((x[per].w if kind == "単" else x[per].p) for x in ds)
            lst = sorted([y for x in ds for y in (x[per].ws if kind == "単" else x[per].ps)], reverse=True)
            return (n, s / n if n else 0, (s - (lst[0] if lst else 0)) / n if n else 0,
                    sum(lst[:3]) / s if s else 0, sum(x[per].t3 for x in ds) / n if n else 0)
        res["A"][kind] = (len(pickA), roi(pickA, "確認"), roi(pickA, "テスト"))
        res["B"][kind] = (len(pickB), roi([d for _, d in pickB], "テスト"))
        res.setdefault("Bd", []).extend((kind, key[1], d["テスト"]) for key, d in pickB)
        for key, d in pickB:
            t = d["テスト"]
            if t.n >= 10:
                rt = (t.w if kind == "単" else t.p) / t.n
                res["surv"].append((key, kind, d["発見"].n, d["確認"].n, t.n,
                                    (d["発見"].w if kind == "単" else d["発見"].p) / d["発見"].n,
                                    (d["確認"].w if kind == "単" else d["確認"].p) / d["確認"].n, rt, t.t3 / t.n))
    return res


def main():
    by_r, _ = load()
    rows = [r for hs in by_r.values() for r in hs]
    L = ["# 高配当に絡む条件の総当たり探索（自動生成, tools/angle_search.py）", "",
         "- 単勝・複勝の実際の払戻。人気は確定人気。発見 〜2022 / 確認 2023-24 / テスト 2025〜。",
         "- 段階A: 発見期間だけで回収率120%以上の組を選び、その組を全部買ったときの確認・テスト期間の回収率（未来のデータ）。",
         "- 段階B: 発見・確認の両期間で120%以上の組を選び、テスト期間の回収率。",
         "- 『でたらめ』= 馬をランダムに400グループに割り振った意味のない条件。これと同程度なら偶然。",
         "- 最大除く = 一番大きい払戻を除いた回収率。上位3本 = 払戻に占める上位3本の割合。", ""]
    L += ["| 角度 | 券種 | 発見で選んだ組 | A: 確認 回収(最大除く) | A: テスト 回収(最大除く) | A: テスト上位3本 | B: 組数 | B: テスト 回収 | B: テスト頭数 |",
          "|---|---|--:|--:|--:|--:|--:|--:|--:|"]
    allsurv = []
    port = {}
    for name, f in list(ANGLES.items()) + [("でたらめ（基準）", fake)]:
        min_n = 40 if name != "でたらめ（基準）" else 40
        res = run_angle(rows, f, min_n)
        for kind in ("単", "複"):
            nA, c, t = res["A"][kind]
            nB, tb = res["B"][kind]
            L.append(f"| {name} | {kind} | {nA} | {c[1]:.0f}%({c[2]:.0f}%) | {t[1]:.0f}%({t[2]:.0f}%) | {t[3]:.0%} | "
                     f"{nB} | {tb[1]:.0f}% | {tb[0]} |")
        for s in res["surv"]:
            allsurv.append((name, *s))
        for kind, popb, t in res.get("Bd", []):
            port.setdefault((name == "でたらめ（基準）", kind, popb in ("4-6人気", "7-9人気")), []).append(t)
        print(name, flush=True)
    # 生き残り（発見・確認とも120%以上で、テストでも100%以上）
    good = [s for s in allsurv if s[0] != "でたらめ（基準）" and s[8] >= 100]
    L += ["", "## 発見・確認とも120%以上で、テスト（2025〜）でも100%以上だった組（テスト頭数の多い順）", "",
          "| 角度 | 条件 | 人気帯 | 券種 | 頭数(発見/確認/テスト) | 回収(発見/確認/テスト) | テスト3着内率 |", "|---|---|---|---|--:|--:|--:|"]
    for name, (k, p), kind, n0, n1, n2, r0, r1, r2, t3 in sorted(good, key=lambda x: -x[6])[:80]:
        L.append(f"| {name} | {' / '.join(map(str, k))} | {p} | {kind} | {n0}/{n1}/{n2} | {r0:.0f}% / {r1:.0f}% / {r2:.0f}% | {t3:.0%} |")
    L += ["", "## 段階Bの組をまとめて買った場合のテスト期間（2025〜）の回収率", "",
          "| 条件の種類 | 券種 | 人気帯 | 頭数 | 回収率 | 最大除く | 上位3本 | 3着内率 |", "|---|---|---|--:|--:|--:|--:|--:|"]
    for (is_null, kind, mid), ts in sorted(port.items()):
        n = sum(t.n for t in ts)
        s_ = sum((t.w if kind == "単" else t.p) for t in ts)
        lst = sorted([y for t in ts for y in (t.ws if kind == "単" else t.ps)], reverse=True)
        if not n:
            continue
        L.append(f"| {'でたらめ' if is_null else '実際の条件'} | {kind} | {'4〜9人気' if mid else '1〜3人気・10人気↓'} | {n} | "
                 f"{s_ / n:.0f}% | {(s_ - (lst[0] if lst else 0)) / n:.0f}% | {sum(lst[:3]) / s_ if s_ else 0:.0%} | "
                 f"{sum(t.t3 for t in ts) / n:.0%} |")
    import json
    from keiba.config import write_atomic
    write_atomic(ROOT / "data" / "knowledge" / "robust_angles.json", json.dumps({
        "_meta": "tools/angle_search.py が生成。〜2022・2023-24で回収率120%以上、2025〜でも100%以上を保った（角度×人気帯）。予想では材料として表示（スコアには足さない）",
        "angles": [{"angle": name, "key": list(k), "pop": p, "kind": kind, "n": [n0, n1, n2],
                    "roi": [round(r0), round(r1), round(r2)], "t3_test": round(t3, 3)}
                   for name, (k, p), kind, n0, n1, n2, r0, r1, r2, t3 in good]}, ensure_ascii=False, indent=1))
    nul = [s for s in allsurv if s[0] == "でたらめ（基準）"]
    L += ["", f"- でたらめな条件で同じ手順を通った組: {len(nul)}（うちテストでも100%以上: {sum(1 for s in nul if s[8] >= 100)}）"]
    (ROOT / "docs" / "analysis" / "angles.md").write_text("\n".join(L) + "\n", encoding="utf-8")
    print("ok")


if __name__ == "__main__":
    main()
