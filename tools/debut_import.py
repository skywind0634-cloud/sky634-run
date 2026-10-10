"""新馬戦の過去成績を JRA 公式から取り込み、別DB data/debut.db に保存する（本体の keiba.db は7R以降専用なので混ぜない）.
使い方: python tools/debut_import.py <開始日> <終了日> <取り込みに使う分数>
- 第6レース以前の成績ページだけを見て、新馬戦だけを保存する（取り込み済みの開催日は飛ばすので、再実行で続きから）
- 馬の血統は、本体DBにいる馬はそこから写し、いない馬だけ取りに行く"""
import datetime as dt
import os
import sqlite3
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from keiba import db, pipeline  # noqa: E402

P = Path("data/debut.db")
conn = sqlite3.connect(str(P))
conn.row_factory = sqlite3.Row
conn.executescript(db.SCHEMA)
if conn.execute("SELECT COUNT(*) FROM horses").fetchone()[0] == 0 and Path("data/keiba.db").exists():
    conn.execute("ATTACH 'data/keiba.db' AS m")
    conn.execute("INSERT OR IGNORE INTO horses SELECT * FROM m.horses")
    conn.commit()
    conn.execute("DETACH m")


def debut_only(race_no=None, grade=None, surface=None, name=None):
    if grade is None and name is None:          # レース番号だけの段階: 新馬戦は第6レース以前
        return race_no is None or race_no <= 6
    return grade == "新馬" or bool(name and "新馬" in name)


pipeline.is_target_race = debut_only
start, end = dt.date.fromisoformat(sys.argv[1]), dt.date.fromisoformat(sys.argv[2])
deadline = time.time() + float(sys.argv[3]) * 60
n, done = pipeline.update_results_jra(conn, start, end, with_pedigree=True, deadline=deadline, newest_first=True)
total = conn.execute("SELECT COUNT(*) FROM races").fetchone()[0]
print(f"新馬戦 取り込み: {n} レース（累計 {total}）{'・完了' if done else '・時間切れ（再実行で続きから）'}")
if os.environ.get("GITHUB_OUTPUT"):
    with open(os.environ["GITHUB_OUTPUT"], "a") as f:
        f.write(f"pending={'false' if done else 'true'}\nimported={n}\n")
