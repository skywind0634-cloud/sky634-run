"""5代血統表の補完（牝系の3〜5代母・5代以内のクロス）.

JRA の馬ページは2代母（母の母）まで。netkeiba の5代血統表（db.netkeiba.com の無料ページ）を馬ごとに取得し、
- data/tail_female.json: {2代母: [3代母, 4代母, 5代母]}（同じ2代母の馬は牝系が共通）
- data/ped5.json: {horse_id: {"x": [[祖先, "4×3"], ...], "t": [3代母, 4代母, 5代母]}}（5代以内のクロス）
に保存する（血統表そのものは保存せず、必要な要約だけ）。GitHub Actions（tail-female.yml）で少しずつ実行し、
出馬表（cards/）の馬 → 新しい世代の馬 の順に取得する。
"""
from __future__ import annotations

import json
import time

from .config import DATA_DIR, ROOT

PATH = DATA_DIR / "tail_female.json"
PATH5 = DATA_DIR / "ped5.json"
_C: dict = {}


def _read(p):
    if not p.exists():
        return {}
    m = p.stat().st_mtime
    if _C.get(p, (None,))[0] != m:
        try:
            _C[p] = (m, json.loads(p.read_text(encoding="utf-8")))
        except ValueError:
            _C[p] = (m, {})
    return _C[p][1]


def load() -> dict:
    return _read(PATH).get("dd", {})


def load5() -> dict:
    return _read(PATH5).get("horses", {})


def crosses(horse_id: str | None) -> list | None:
    """5代血統表から計算済みのクロス（無ければ None）."""
    h = load5().get(horse_id or "")
    return [tuple(x) for x in h["x"]] if h else None


def save(dd: dict, h5: dict) -> None:
    PATH.write_text(json.dumps({"_meta": "2代母 → [3代母, 4代母, 5代母]（keiba/tailfemale.py）", "dd": dd},
                               ensure_ascii=False, indent=0, sort_keys=True), encoding="utf-8")
    PATH5.write_text(json.dumps({"_meta": "horse_id → x: 5代以内のクロス, t: [3代母,4代母,5代母]（keiba/tailfemale.py）",
                                 "horses": h5}, ensure_ascii=False, separators=(",", ":"), sort_keys=True), encoding="utf-8")


def pending(conn) -> list[str]:
    done = load5()
    card_ids = []
    for f in sorted((ROOT / "cards").glob("*/*.json"), reverse=True)[:400]:
        try:
            card_ids += [e.get("horse_id") for e in json.loads(f.read_text(encoding="utf-8")).get("entries", [])]
        except (ValueError, OSError):
            continue
    rest = [r[0] for r in conn.execute("SELECT horse_id FROM horses ORDER BY horse_id DESC")]
    out, seen = [], set(done)
    for hid in card_ids + rest:
        if hid and hid not in seen and hid[:4].isdigit():
            seen.add(hid)
            out.append(hid)
    return out


def run(conn, budget_min: float = 50.0, limit: int | None = None) -> tuple[int, int]:
    from . import knowledge as K
    from .scraper import netkeiba as NK
    dd, h5 = dict(load()), dict(load5())
    todo = pending(conn)
    deadline = time.time() + budget_min * 60
    n = 0
    for hid in todo[:limit] if limit else todo:
        if time.time() > deadline:
            break
        try:
            p = NK.fetch_pedigree(hid)
        except Exception as e:   # noqa: BLE001
            print("skip", hid, e)
            continue
        if not p:
            continue
        p = {k: v.split("(")[0].strip() for k, v in p.items() if v}
        tf = [p.get("DDD"), p.get("DDDD"), p.get("DDDDD")]
        h5[hid] = {"x": [list(x) for x in K.detect_crosses(p)[:6]], "t": tf}
        if p.get("DD"):
            dd.setdefault(p["DD"], tf)
        n += 1
        if n % 200 == 0:
            save(dd, h5)
            print(n, "saved", flush=True)
    save(dd, h5)
    return n, len(todo) - n
