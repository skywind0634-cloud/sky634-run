"""過去レースのコース別血統（keiba/digest.py の course_blood_horses）を馬ごとに記録する（2026-11-08 ユーザー「コース別血統の指標もね」）.
出力: data/cache/course_blood_rows.json {race_id: {馬番: [○の数, ▼の数]}}。tools/set_formation_search.py の集まり CB（○が▼より多い）に使う.
注意: data/knowledge/course_blood.json は 2021-23 と 2024-26 で選んでいるので、2025-26 の確かめは選んだ期間の中（甘め）.
使い方: python3 tools/course_blood_rows.py <開始日> <終了日> [並列数]"""
import json, sqlite3, sys
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT)); sys.path.insert(0, str(ROOT / "tools"))


def run(args):
    start, end = args
    import flag_backtest as FB
    from keiba import digest as D
    conn = sqlite3.connect(ROOT / "data" / "keiba.db")
    out = {}
    for R, ents in FB.cards(conn, start, end):
        card = dict(R); card["entries"] = ents
        evals = [SimpleNamespace(number=e["number"], name=str(e["number"]), sire=e["sire"], damsire=e["damsire"], sire_line=e["_sl"] or "",
                                 damsire_line=e["_dsl"] or "", pop_rank=e["popularity"], odds=e["odds"]) for e in ents]
        try:
            cb = D.course_blood_horses(card, evals)
        except Exception:  # noqa: BLE001
            continue
        if cb:
            out[R["race_id"]] = {str(n): [t.count("○"), t.count("▼")] for n, t in cb}
    return out


def main(start, end, workers=4):
    import datetime as dt
    d0, d1 = dt.date.fromisoformat(start), dt.date.fromisoformat(end)
    chunks, d = [], d0
    while d <= d1:
        e = min(d + dt.timedelta(days=30), d1); chunks.append((d.isoformat(), e.isoformat())); d = e + dt.timedelta(days=1)
    res = {}
    with ProcessPoolExecutor(workers) as ex:
        for r in ex.map(run, chunks):
            res.update(r)
    json.dump(res, open(ROOT / "data" / "cache" / ("course_blood_rows" + __import__("os").environ.get("CB_SFX", "") + ".json"), "w"))
    print(len(res))


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2], int(sys.argv[3]) if len(sys.argv) > 3 else 4)
