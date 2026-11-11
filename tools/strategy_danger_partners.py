"""「危険な人気馬」の判定と、妙味条件(厳格)軸の3連複の相手選びを検証（2026-10-11）.

データ: data/cache/strategy_backtest.json（2025-10〜2026-09・1555レース・実払戻）。前半/後半＝2026-04-01で分割。
位置取りの特徴（tools/position_jockey_analysis.py と同じ作り方・そのレースより前の情報だけ）を data/keiba.db から付ける。
使い方: python3 tools/strategy_danger_partners.py → docs/analysis/danger_partners.md
"""
from __future__ import annotations

import json
import sqlite3
import statistics
import sys
from collections import defaultdict
from itertools import combinations
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
from position_jockey_analysis import first_last, load  # noqa: E402

OUT = ROOT / "docs" / "analysis" / "danger_partners.md"


def position_flags(target: set[str]) -> dict:
    """(race_id, 馬番) → 位置取りの特徴."""
    races, rows = load()
    order = sorted(races, key=lambda r: (races[r]["date"], r))
    for rid in order:
        ts = [x["margin"] for x in rows[rid] if x["margin"]]
        w = min(ts) if ts else None
        for x in rows[rid]:
            x["margin"] = round(x["margin"] - w, 1) if (w is not None and x["margin"]) else None
    hist = defaultdict(list); jstat = defaultdict(lambda: defaultdict(lambda: [0, 0, 0]))
    out = {}
    for rid in order:
        R = races[rid]; n = R["n"] or len(rows[rid]); yr = int(R["date"][:4]); ent = rows[rid]
        if rid in target:
            prof = {}
            for x in ent:
                h = hist[x["hid"]][-3:]
                fr = [p["fr"] for p in h if p["fr"] is not None]
                prof[x["hid"]] = (sum(fr) / len(fr) if fr else None, h)
            front_n = sum(1 for fr, _ in prof.values() if fr is not None and fr <= 0.2)
            for x in ent:
                fr, h = prof[x["hid"]]
                f = set()
                if fr is not None and len(h) >= 2:
                    last = h[-1]
                    if fr <= 0.2 and (last["fr"] or 1) <= 0.25 and (last["margin"] or 9) <= 0.5:
                        f.add("先行粘り")  # 逃げ先行型 × 前走先行0.5秒差以内（7〜12人気でA/E 1.34/1.24）
                    if front_n >= 4 and fr >= 0.55 and last["j"] == x["j"]:
                        f.add("差し展開")  # 前に行く馬4頭以上 × 差し追込 × 継続騎乗（A/E 1.32/1.30）
                out[(rid, x["num"])] = f
        for x in ent:
            fr, lr = first_last(x["passing"], n)
            hist[x["hid"]].append(dict(fr=fr, lr=lr, fin=x["fin"], margin=x["margin"], j=x["j"]))
    return out


def P(r, kind, combo):
    key = "-".join(map(str, sorted(combo))) if len(combo) > 1 else str(combo[0])
    for c, y in r["pay"].get(kind, []):
        if c == key:
            return y
    return 0


def main():
    d = json.load(open(ROOT / "data" / "cache" / "strategy_backtest.json"))
    flags = position_flags({r["race_id"] for r in d})
    half = lambda r: "前" if r["date"] < "2026-04-01" else "後"
    L = ["# 「危険な人気馬」と、妙味条件(厳格)軸の3連複の相手選びの検証（自動生成, tools/strategy_danger_partners.py）", "",
         "- 過去1年（2025-10〜2026-09・1555レース）の実払戻。前半/後半＝2026-04-01で分割。", ""]
    # 1. 危険な人気馬
    L += ["## 1. 危険な人気馬（人気帯の中で走る条件が一定以下の1〜6番人気）", "",
          "| 対象 | 頭数 前/後 | 3着内率 前/後 | 同じ人気の他の馬 | 単勝回収 前/後 | 複勝回収 前/後 |", "|---|--:|--:|--:|--:|--:|"]
    for lo, hi in ((1, 3), (4, 6)):
        for th in (-0.3, -0.5):
            s = {k: {"in": [0, 0, 0, 0], "out": [0, 0]} for k in "前後"}
            for r in d:
                for h in r["horses"]:
                    if not (lo <= h["pop"] <= hi) or h["fin"] is None or h["cond"] is None:
                        continue
                    t = s[half(r)]
                    if h["cond"] <= th:
                        a = t["in"]; a[0] += 1; a[1] += h["fin"] <= 3; a[2] += P(r, "単勝", (h["num"],)); a[3] += P(r, "複勝", (h["num"],))
                    else:
                        t["out"][0] += 1; t["out"][1] += h["fin"] <= 3
            a, b = s["前"], s["後"]
            L.append(f"| {lo}〜{hi}番人気・走る条件{th}以下 | {a['in'][0]}/{b['in'][0]} | {a['in'][1]/a['in'][0]:.0%} / {b['in'][1]/b['in'][0]:.0%} | "
                     f"{a['out'][1]/a['out'][0]:.0%} / {b['out'][1]/b['out'][0]:.0%} | {a['in'][2]/a['in'][0]:.0f}% / {b['in'][2]/b['in'][0]:.0f}% | "
                     f"{a['in'][3]/a['in'][0]:.0f}% / {b['in'][3]/b['in'][0]:.0f}% |")
    # 2. 相手選び
    def danger(h):
        return h["pop"] <= 6 and h["cond"] is not None and h["cond"] <= -0.3

    def build(r, axis, rule):
        hs = [h for h in r["horses"] if h["num"] != axis["num"]]
        fav = {h["pop"]: h for h in hs}
        col2 = [fav[p]["num"] for p in (1, 2) if p in fav]
        bym = sorted(hs, key=lambda h: -h["p"])
        if rule == "現行: 1〜2番人気 − モデル上位5頭":
            col3 = [h["num"] for h in bym[:5]]
        elif rule == "危険な人気馬を相手から外す":
            col2 = [fav[p]["num"] for p in (1, 2, 3) if p in fav and not danger(fav[p])][:2]
            col3 = [h["num"] for h in bym if not danger(h)][:5]
        elif rule == "モデル上位5頭＋位置取りの特徴がある馬":
            col3 = [h["num"] for h in bym[:5]] + [h["num"] for h in hs if flags.get((r["race_id"], h["num"]))]
        elif rule == "モデル上位4頭＋位置取りの特徴がある馬（最大2頭）":
            extra = [h["num"] for h in bym[4:] if flags.get((r["race_id"], h["num"]))][:2]
            col3 = [h["num"] for h in bym[:4]] + extra
        elif rule == "相手を3〜7番人気に":
            col3 = [fav[p]["num"] for p in range(3, 8) if p in fav]
        elif rule == "2列目をモデル上位2頭に":
            col2 = [h["num"] for h in bym[:2]]
            col3 = [h["num"] for h in bym[:6]]
        else:
            raise ValueError(rule)
        out = set()
        for b in col2:
            for c in dict.fromkeys(col3):
                if c not in (axis["num"], b):
                    out.add(tuple(sorted((axis["num"], b, c))))
        return out

    rules = ["現行: 1〜2番人気 − モデル上位5頭", "危険な人気馬を相手から外す", "モデル上位5頭＋位置取りの特徴がある馬",
             "モデル上位4頭＋位置取りの特徴がある馬（最大2頭）", "相手を3〜7番人気に", "2列目をモデル上位2頭に"]
    L += ["", "## 2. 妙味条件(厳格)軸の3連複の相手選び（軸＝妙味条件(厳格)に該当する4番人気以下）", "",
          "| 相手の選び方 | 点数/軸 | 回収率 前/後 | 的中率(軸ごと) 前/後 | 的中時の払戻中央値 |", "|---|--:|--:|--:|--:|"]
    nflag = sum(1 for v in flags.values() if v)
    for rule in rules:
        s = {k: [0, 0, 0, 0] for k in "前後"}; pays = []
        for r in d:
            for a in r["horses"]:
                if not (a["seg"] and a["pop"] >= 4):
                    continue
                t = s[half(r)]; tk = build(r, a, rule); ret = sum(P(r, "3連複", c) for c in tk)
                t[0] += 100 * len(tk); t[1] += ret; t[2] += 1; t[3] += ret > 0
                if ret:
                    pays.append(ret)
        a, b = s["前"], s["後"]
        L.append(f"| {rule} | {(a[0]+b[0])/100/(a[2]+b[2]):.1f} | {a[1]/a[0]:.0%} / {b[1]/b[0]:.0%} | {a[3]/a[2]:.0%} / {b[3]/b[2]:.0%} | "
                 f"{statistics.median(pays) if pays else 0:,.0f}円 |")
    L += ["", f"- 位置取りの特徴がある馬: 対象レースの延べ {nflag} 頭（先行粘り＝普段から前20%で前走も先行0.5秒差以内、差し展開＝前に行く馬4頭以上×差し追込×継続騎乗）。"]
    OUT.write_text("\n".join(L) + "\n", encoding="utf-8")
    print("\n".join(L))


if __name__ == "__main__":
    main()
