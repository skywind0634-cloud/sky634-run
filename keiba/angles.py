"""検証済みの傾向（角度×人気帯）: tools/angle_search.py が見つけ、2022まで・2023-24・2025〜の3期間で回収率100%超を保った条件.

予想では「材料」として根拠欄・注目馬一覧に出す（スコアには足さない。妙味条件・走る条件と二重に数えないため）。
"""
from __future__ import annotations

import json

from .config import KNOWLEDGE_DIR

PATH = KNOWLEDGE_DIR / "robust_angles.json"


def gate_group(g):
    if not g:
        return None
    return "内枠(1-3)" if g <= 3 else ("中枠(4-6)" if g <= 6 else "外枠(7-8)")


def b_fin(x):
    return None if not x else ("前走1-3着" if x <= 3 else "前走4-9着" if x <= 9 else "前走10着↓")


def b_pop(x):
    return None if not x else ("前走1-3人気" if x <= 3 else "前走4-9人気" if x <= 9 else "前走10人気↓")


def sex_age(r):
    a = r.get("age") or 0
    return f"{r.get('sex')}{min(a, 6)}歳{'↑' if a >= 6 else ''}"


def pop_band(p):
    return None if not p else "1-3人気" if p <= 3 else "4-6人気" if p <= 6 else "7-9人気" if p <= 9 else "10人気↓"


def crs(r):
    return f"{r['course']}{r['surface']}{r['distance']}"


def dband(r):
    d = r["distance"]
    return f"{r['surface']}{'〜1200' if d <= 1200 else '1300-1400' if d <= 1400 else '1500-1700' if d <= 1700 else '1800-2200' if d <= 2200 else '2300〜'}"


def going(r):
    return "道悪" if r.get("going") in ("重", "不良") else "良・稍重"


def wake(r):
    return f"{r['course']}{r['surface']}"


ANGLES = {
    "父×コース": lambda r: (r["sire"], crs(r)),
    "父×競馬場芝ダ": lambda r: (r["sire"], wake(r)),
    "父×距離帯": lambda r: (r["sire"], dband(r)),
    "父×馬場": lambda r: (r["sire"], r["surface"], going(r)),
    "父系統×コース": lambda r: (r["sire_line"], crs(r)),
    "母父×距離帯": lambda r: (r["damsire"], dband(r)),
    "母父系統×コース": lambda r: (r["damsire_line"], crs(r)),
    "父×母父系統": lambda r: (r["sire"], r["damsire_line"], r["surface"]),
    "騎手×コース": lambda r: (r["jockey"], crs(r)),
    "騎手×競馬場芝ダ": lambda r: (r["jockey"], wake(r)),
    "調教師×競馬場芝ダ": lambda r: (r["trainer"], wake(r)),
    "騎手×調教師": lambda r: (r["jockey"], r["trainer"]),
    "枠×コース": lambda r: (gate_group(r["gate"]), crs(r)),
    "前走脚質×コース": lambda r: (r["prev_style"], crs(r)),
    "距離変化×コース": lambda r: (r["dchg"], crs(r)),
    "前走着順×コース": lambda r: (b_fin(r.get("prev_fin")), crs(r)),
    "人気落ち×距離帯": lambda r: (b_pop(r.get("prev_pop")), dband(r)),
    "ローテ×距離帯": lambda r: (r["interval"], dband(r)),
    "性齢×距離帯": lambda r: (sex_age(r), dband(r)),
    "父×ローテ": lambda r: (r["sire"], r["interval"]),
}

_CACHE: dict = {}


def _load() -> list:
    if not PATH.exists():
        return []
    m = PATH.stat().st_mtime
    if _CACHE.get("m") != m:
        try:
            _CACHE.update(m=m, d=json.loads(PATH.read_text(encoding="utf-8"))["angles"])
        except (OSError, ValueError, KeyError):
            _CACHE.update(m=m, d=[])
    return _CACHE["d"]


def match(r: dict, popularity) -> list[str]:
    """この馬（レース前に分かる情報）に当てはまる検証済みの傾向の説明文."""
    pb = pop_band(popularity)
    if not pb:
        return []
    out = []
    for a in _load():
        if a["pop"] != pb:
            continue
        f = ANGLES.get(a["angle"])
        try:
            k = f(r) if f else None
        except (KeyError, TypeError):
            continue
        if k is None or [str(x) for x in k] != [str(x) for x in a["key"]]:
            continue
        rr = " / ".join(f"{x:.0f}%" for x in a["roi"])
        out.append(f"検証済みの傾向: {a['angle']}＝{' / '.join(map(str, a['key']))}（{pb}） "
                   f"{a['kind']}勝回収率 {rr}（〜2022 / 2023-24 / 2025〜, {sum(a['n'])}頭）")
    return out
