"""今日の出馬表から人気・オッズを消した「前日と同じ条件（適性だけ）」の digest を作る（2026-11-07）.
使い方: python3 tools/preday_blind.py <日付> <出力digest>  → その後 race_sheet と tools/merge_preday.py で当日版と統合する。
"""
import json
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT)); sys.path.insert(0, str(ROOT / "tools"))
from preday_backtest import digest_text  # noqa: E402


def main(day, out):
    with tempfile.TemporaryDirectory() as tmp:
        dst = Path(tmp) / day; dst.mkdir()
        for f in (ROOT / "cards" / day).glob("*.json"):
            d = json.loads(f.read_text(encoding="utf-8"))
            if isinstance(d, dict) and d.get("entries"):
                for e in d["entries"]:
                    e["odds"] = None; e["popularity"] = None
                for k in [k for k in d if "odds" in k.lower()]:
                    d.pop(k)
            (dst / f.name).write_text(json.dumps(d, ensure_ascii=False), encoding="utf-8")
        Path(out).write_text(digest_text(day, Path(tmp)), encoding="utf-8")


if __name__ == "__main__":
    main(*sys.argv[1:])
