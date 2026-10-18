"""期待値で選ぶ3連複・ワイド（2026-10-18, tools/combo_value.py で検証）.
市場の3着内確率（単勝・複勝オッズ）に、フラグ（○◎数・×▽▼数）を足したロジスティック回帰で3着内確率を作り、
馬ごとの上乗せ（こちら÷市場）の積が閾値以上の組を、発売中の組み合わせオッズの範囲内から選ぶ。
2022-23 で学習し、2024 / 2025-26 で 3連複（比1.7以上・100〜1000倍・最大10点）127%/415%、ワイド（比1.5以上・10〜50倍・最大5点）158%/201%。
"""
from __future__ import annotations

import json
import math

from .config import DATA_DIR

MODEL = DATA_DIR / "knowledge" / "combo_value_model.json"
SPECS = {"3連複": ("trio", 1.7, 100, 1000, 10), "ワイド": ("wide", 1.5, 10, 50, 5)}


def _feats(win: float, plc: float, n: int, plus: int, minus: int):
    lw, lp = math.log(win), math.log(plc)
    a = [1.0, lw, lp, lw * lw, math.log(n)]
    b = [min(plus, 6), min(minus, 6), min(plus, 6) * (lw > math.log(15)), min(minus, 6) * (lw > math.log(15))]
    return a, a + b


def lifts(odds: dict, marks: dict[int, tuple[int, int]]) -> dict[int, float]:
    """馬番 → 3着内確率の上乗せ（こちら÷市場）. odds は JRA の最終/発売中オッズ（tanpuku: {馬番: [単勝, 複勝下限, 複勝上限]}）."""
    if not MODEL.exists():
        return {}
    w = json.loads(MODEL.read_text())
    tp = {int(k): v for k, v in (odds.get("tanpuku") or {}).items() if v and v[0] and v[1]}
    n = len(tp)
    out = {}
    for num, v in tp.items():
        plus, minus = marks.get(num, (0, 0))
        a, b = _feats(v[0], (v[1] + (v[2] or v[1])) / 2, n, plus, minus)
        pa = 1 / (1 + math.exp(-sum(x * y for x, y in zip(w["wa"], a))))
        pb = 1 / (1 + math.exp(-sum(x * y for x, y in zip(w["wb"], b))))
        out[num] = pb / pa
    return out


def picks(odds: dict, marks: dict[int, tuple[int, int]]) -> dict[str, list[tuple[str, float, float]]]:
    """券種 → [(組, オッズ, 期待値の比)]（比の高い順）."""
    lf = lifts(odds, marks)
    out = {}
    for kind, (key, th, lo, hi, nmax) in SPECS.items():
        cand = []
        for combo, o in (odds.get(key) or {}).items():
            o = o[0] if isinstance(o, list) else o
            ns = [int(x) for x in combo.split("-")]
            if not o or not (lo <= o <= hi) or any(x not in lf for x in ns):
                continue
            r = math.prod(lf[x] for x in ns)
            if r >= th:
                cand.append((combo, o, r))
        out[kind] = sorted(cand, key=lambda x: -x[2])[:nmax]
    return out
