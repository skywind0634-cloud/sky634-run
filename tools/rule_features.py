"""過去レースの全馬に、予想で使う材料（book_condition / pace_l3 / course_check の各ルール）を1つずつ記録する（2026-10-24, ユーザー「精度上げろ」）.
フラグ点（○は+1・×は−1の単純な足し算）をやめて、ルールごとの重さを学ぶための元データ。tools/flag_backtest.py の作り直しを流用。
出力: data/cache/rule_rows.json（1頭1行: date, rid, num, pop, odds, fin, rules=[(ルール名, 記号)], fuku, tan）
使い方: python3 tools/rule_features.py 2021-01-01 2026-10-18 [並列数]
"""
import json, re, sqlite3, sys
from collections import defaultdict
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tools"))
from flag_backtest import cards  # noqa: E402

RULE = re.compile(r"([^、：（）]+?)\s*([◎○×▽▼])（")


def run(args):
    start, end = args
    from keiba import digest as D
    conn = sqlite3.connect(ROOT / "data" / "keiba.db")
    out = []
    for R, ents in cards(conn, start, end):
        card = dict(R); card["entries"] = ents
        evals = [SimpleNamespace(number=e["number"], name=str(e["number"]), sire=e["sire"], damsire=e["damsire"], sire_line=e["_sl"] or "",
                                 damsire_line=e["_dsl"] or "", pop_rank=e["popularity"], odds=e["odds"]) for e in ents]
        rules = defaultdict(list)
        for f in (D.book_condition_horses, D.pace_l3_horses, D.course_check_horses):
            try:
                for num, t in f(card, evals):
                    for name, mk in RULE.findall(t):
                        name = re.sub(r"[+-]?\d+(\.\d+)?秒|（.*", "", name).strip(" 　")
                        rules[num].append((f.__name__[:4] + ":" + name[:60], mk))
            except Exception:  # noqa: BLE001
                pass
        pay = json.loads(R["payouts"]) if R["payouts"] else {}
        fk = {a: y for a, y in pay.get("複勝", [])}; tk = {a: y for a, y in pay.get("単勝", [])}
        for e in ents:
            out.append(dict(date=R["date"], rid=R["race_id"], num=e["number"], pop=e["popularity"], odds=e["odds"], fin=e["_fin"],
                            n=len(ents), rules=rules.get(e["number"], []), fuku=fk.get(str(e["number"]), 0), tan=tk.get(str(e["number"]), 0)))
    return out


def main(start, end, workers=4):
    import datetime as dt
    d0, d1 = dt.date.fromisoformat(start), dt.date.fromisoformat(end)
    chunks, d = [], d0
    while d <= d1:
        e = min(d + dt.timedelta(days=20), d1)
        chunks.append((d.isoformat(), e.isoformat())); d = e + dt.timedelta(days=1)
    rows = []
    with ProcessPoolExecutor(workers) as ex:
        for i, r in enumerate(ex.map(run, chunks)):
            rows += r
            if i % 10 == 0:
                print(i, len(chunks), len(rows), flush=True)
    json.dump(rows, open(ROOT / "data" / "cache" / "rule_rows.json", "w"), ensure_ascii=False)
    print("done", len(rows))


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2], int(sys.argv[3]) if len(sys.argv) > 3 else 4)
