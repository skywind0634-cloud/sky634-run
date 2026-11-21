"""results.odds（単勝オッズ）の抜けを埋める（2026-11-21 発見: JRA の結果ページには単勝オッズの列が無く、
2026-10-17 以降の取り込みでは勝ち馬以外のオッズが空になっていた。人気・払戻はある）.
埋める元: ①odds ブランチの JRA 最終オッズ（data/cache/odds/<YYYYMM>.json.gz の tanpuku）、②day-results の結果（netkeiba の単勝オッズ）.
使い方: python3 tools/fill_odds.py [day-results の JSON ...]
"""
import glob, gzip, json, sqlite3, sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def main(paths):
    c = sqlite3.connect(ROOT / "data" / "keiba.db")
    miss = {(rid, num) for rid, num in c.execute("select race_id, number from results where odds is null")}
    n0 = len(miss); fixed = 0
    for f in sorted(glob.glob(str(ROOT / "data" / "cache" / "odds" / "*.json.gz"))):
        d = json.load(gzip.open(f))
        for rid, rec in d.items():
            for num, v in (rec.get("tanpuku") or {}).items():
                k = (rid, int(num))
                if k in miss and v and v[0]:
                    c.execute("update results set odds=? where race_id=? and number=?", (float(v[0]), rid, int(num)))
                    miss.discard(k); fixed += 1
    for p in paths:
        for r in json.load(open(p)):
            for row in r.get("rows", []):
                try:
                    k = (r["race_id"], int(row[2])); od = float(row[10])
                except Exception:
                    continue
                if k in miss:
                    c.execute("update results set odds=? where race_id=? and number=?", (od, *k))
                    miss.discard(k); fixed += 1
    c.commit()
    print(f"単勝オッズの抜け {n0} → 埋めた {fixed}・残り {len(miss)}")


if __name__ == "__main__":
    main(sys.argv[1:])
