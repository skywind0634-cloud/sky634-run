"""5代血統表をまるごと保存する（2026-10-11）. 祖先62頭を位置の順に並べて data/ped5_full.json に保存.

位置: 'S'=父, 'D'=母, 'SD'=父の母, 'SDS'=父母父, 'DDS'=母母父 …（S/Dを5文字まで）。
保存形式: {"pos": [位置の並び], "horses": {horse_id: [祖先名 …（pos の順）]}}。
対象: data/keiba.db の horses（出馬表の馬 → 新しい世代の順）。取得済みはスキップ。netkeiba の5代血統表（無料ページ）を2秒以上の間隔で取得。
使い方: python3 tools/ped5_full.py <分数> → 出力の最後に pending=true/false と imported=<件数>
"""
from __future__ import annotations

import json
import os
import sqlite3
import sys
import time
from itertools import product
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
PATH = ROOT / "data" / "ped5_full.json"
POS = ["".join(p) for n in range(1, 6) for p in product("SD", repeat=n)]


def load() -> dict:
    if not PATH.exists():
        return {}
    return json.loads(PATH.read_text(encoding="utf-8")).get("horses", {})


def save(h: dict) -> None:
    PATH.write_text(json.dumps({"_meta": "5代血統表（tools/ped5_full.py）。horses の値は pos の順の祖先名", "pos": POS, "horses": h},
                               ensure_ascii=False, separators=(",", ":"), sort_keys=True), encoding="utf-8")


def ancestors(horse_id: str) -> dict:
    """保存済みの5代血統表 → {位置: 馬名}（無ければ空）."""
    v = load().get(horse_id or "")
    return {p: n for p, n in zip(POS, v) if n} if v else {}


def pending(conn, done: dict) -> list[str]:
    card_ids = []
    for f in sorted((ROOT / "cards").glob("*/*.json"), reverse=True)[:400]:
        try:
            card_ids += [e.get("horse_id") for e in json.loads(f.read_text(encoding="utf-8")).get("entries", [])]
        except (ValueError, OSError):
            continue
    rest = [r[0] for r in conn.execute("SELECT horse_id FROM horses ORDER BY horse_id DESC")]
    out, seen = [], set(done)
    for hid in card_ids + rest:
        if hid and hid not in seen and str(hid)[:4].isdigit():
            seen.add(hid); out.append(hid)
    return out


def main(budget_min: float):
    from keiba.scraper import netkeiba as NK
    conn = sqlite3.connect(ROOT / "data" / "keiba.db")
    h = load()
    todo = pending(conn, h)
    deadline = time.time() + budget_min * 60
    n = 0
    for hid in todo:
        if time.time() > deadline:
            break
        try:
            p = NK.fetch_pedigree(hid)
        except Exception as e:  # noqa: BLE001
            print("skip", hid, e); continue
        if not p:
            continue
        h[hid] = [(p.get(k) or "").split("(")[0].strip() for k in POS]
        n += 1
        if n % 300 == 0:
            save(h); print(n, "saved", flush=True)
    save(h)
    left = len(todo) - n
    print(f"imported {n}, left {left}")
    out = os.environ.get("GITHUB_OUTPUT")
    if out:
        with open(out, "a") as f:
            f.write(f"pending={'true' if left > 0 else 'false'}\nimported={n}\n")


if __name__ == "__main__":
    main(float(sys.argv[1]) if len(sys.argv) > 1 else 50)
