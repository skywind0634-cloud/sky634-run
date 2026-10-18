"""今週の対象レースの発売中オッズ（単勝・複勝・馬連・ワイド・3連複）を JRA から取得し、cards/<日付>/odds/<race_id>.json に保存する（2026-10-18）.
keiba/pipeline.load_cards が読み込み、digest の◆期待値3連複・ワイドに使う。
使い方: python tools/fetch_live_odds.py <YYYY-MM-DD> [...]"""
import json, sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from keiba.config import CARDS_DIR  # noqa: E402
from keiba.scraper import jra  # noqa: E402

dates = sys.argv[1:]
want = {}
for d in dates:
    for p in (CARDS_DIR / d).glob("*.json"):
        want[p.stem] = d
got = jra.live_odds(set(dates), set(want))
for rid, rec in got.items():
    out = CARDS_DIR / want[rid] / "odds" / f"{rid}.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(rec, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
print(f"odds saved {len(got)}/{len(want)}")
