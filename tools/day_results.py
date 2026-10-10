"""指定日の JRA 全レース（障害以外）の着順・人気・単勝を取得して JSON に出す（答え合わせ用）.
使い方: python tools/day_results.py <YYYY-MM-DD> <出力json>"""
import datetime as dt
import json
import sqlite3
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from keiba import db, pipeline  # noqa: E402

day = dt.date.fromisoformat(sys.argv[1])
conn = sqlite3.connect(":memory:")
conn.row_factory = sqlite3.Row
conn.executescript(db.SCHEMA)
pipeline.is_target_race = lambda race_no=None, grade=None, surface=None, name=None: surface != "障" and not (name and "障害" in name)
pipeline.update_results_jra(conn, day, day, with_pedigree=False)
out = []
for ra in conn.execute("SELECT * FROM races ORDER BY course, race_no"):
    rs = conn.execute("SELECT r.*, h.name FROM results r LEFT JOIN horses h USING(horse_id) WHERE race_id=? ORDER BY finish IS NULL, finish", (ra["race_id"],)).fetchall()
    out.append({"race_id": ra["race_id"], "course": ra["course"], "race_no": ra["race_no"], "name": ra["name"], "grade": ra["grade"],
                "results": [{"finish": r["finish"], "number": r["number"], "name": r["name"], "popularity": r["popularity"], "odds": r["odds"]} for r in rs]})
Path(sys.argv[2]).write_text(json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8")
print("races", len(out))
