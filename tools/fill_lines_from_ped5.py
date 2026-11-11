"""5代血統表（data/ped5_full.json）の父系をさかのぼって、系統が「その他」・空の父/母父に既知の系統を割り当てる（2026-10-12）.

父: SS→SSS→SSSS、母父: DSS→DSSS→DSSSS の順に、DB で系統が分かっている種牡馬が見つかればその系統にする。
使い方: python3 tools/fill_lines_from_ped5.py <ped5_full.json>
"""
import json
import sqlite3
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def main(path):
    P = json.loads(Path(path).read_text(encoding="utf-8"))
    pos, H = P["pos"], P["horses"]
    c = sqlite3.connect(ROOT / "data" / "keiba.db")
    known = {}
    for q in ("select sire, sire_line from horses", "select damsire, damsire_line from horses"):
        for s, sl in c.execute(q):
            if s and sl and sl != "その他":
                known.setdefault(s, sl)
    n = {"sire_line": 0, "damsire_line": 0}
    for hid, sl, dsl in c.execute("select horse_id, sire_line, damsire_line from horses").fetchall():
        v = H.get(hid)
        if not v:
            continue
        a = dict(zip(pos, v))
        for col, cur, chain in (("sire_line", sl, ("SS", "SSS", "SSSS")), ("damsire_line", dsl, ("DSS", "DSSS", "DSSSS"))):
            if cur and cur != "その他":
                continue
            ln = next((known[a[k]] for k in chain if a.get(k) in known), None)
            if ln:
                c.execute(f"update horses set {col}=? where horse_id=?", (ln, hid))
                n[col] += 1
    c.commit()
    print(n)


if __name__ == "__main__":
    main(sys.argv[1])
