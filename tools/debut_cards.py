"""新馬戦だけの出馬表カードを作る（通常は対象外の7R未満・新馬も含める）.
使い方: python tools/debut_cards.py <YYYY-MM-DD> → cards_debut/<日付>/<race_id>.json"""
import datetime as dt
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from keiba import db, pipeline  # noqa: E402


def debut_only(race_no=None, grade=None, surface=None, name=None):
    if grade is None and name is None:   # レース番号だけの段階では全部通す
        return True
    return grade == "新馬" or bool(name and "新馬" in name)


pipeline.is_target_race = debut_only
day = dt.date.fromisoformat(sys.argv[1])
ps = pipeline.build_cards_jra(db.connect(), [day], out_dir=Path("cards_debut"))
print("cards", len(ps))
