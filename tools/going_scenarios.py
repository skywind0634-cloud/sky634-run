"""馬場ごと（良・稍重・重・不良）の【今日買うもの】を朝にまとめて作る（2026-10-24, ユーザー「馬場状態もあるから途中で今日みたいなことある。良馬場前提だけじゃない」）.
買い目は朝の版で固定し、当日に馬場発表が変わったときだけ、ここで作っておいた該当する馬場の買い目に切り替える（その場で作り直さない）。
使い方: python3 tools/going_scenarios.py <日付> > predictions/<土曜>/馬場別_<日付>.md
"""
import datetime as dt, io, os, re, sys, tempfile
from pathlib import Path
from contextlib import redirect_stdout

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT)); sys.path.insert(0, str(ROOT / "tools"))
from keiba import analysis, db, digest, pipeline, report  # noqa: E402
from keiba.config import is_target_race  # noqa: E402
from keiba.model import evaluate_race  # noqa: E402
import keiba.model as M  # noqa: E402
from keiba.cli import load_params  # noqa: E402
import race_sheet  # noqa: E402

GOINGS = {"芝": ["良", "稍重", "重"], "ダ": ["良", "稍重", "重", "不良"]}


def buy_lines(txt):
    with tempfile.NamedTemporaryFile("w", suffix=".md", delete=False, encoding="utf-8") as f:
        f.write(txt); p = f.name
    try:
        out = race_sheet.card_summary(p).split("\n")
    finally:
        os.unlink(p)
    end = next(i for i, l in enumerate(out) if l.startswith("【参考"))
    return [l for l in out[:end] if l.startswith("  - ") and "なし" not in l]


def main(day):
    M.PARAMS.update(load_params())
    conn = db.connect(); st = analysis.build_stats(conn)
    print(f"# 馬場ごとの【今日買うもの】 {day}（朝に作って固定。馬場発表が変わったら、その馬場の行に切り替えるだけ）\n")
    for c in sorted(pipeline.load_cards(dt.date.fromisoformat(day)), key=lambda c: (c.get("course", ""), c.get("race_no", 0))):
        if not c.get("entries") or not is_target_race(c.get("race_no"), c.get("grade"), c.get("surface"), c.get("name")):
            continue
        res = []
        for g in GOINGS.get(c.get("surface"), ["良"]):
            cc = dict(c); cc["going"] = g
            txt = digest.text(cc, evaluate_race(cc, st, conn, n_sims=0), report.race_title(cc))
            res.append((g, buy_lines(txt)))
        print(f"## {c['course']}{c['race_no']}R {c.get('name','')} {c.get('surface')}{c.get('distance')}（朝の発表: {c.get('going') or '未発表'}）")
        seen = []
        for g, lines in res:
            for i, (g2, l2) in enumerate(seen):
                if l2 == lines:
                    seen[i] = (g2 + "・" + g, l2); break
            else:
                seen.append((g, lines))
        for g, lines in seen:
            print(f"- **{g}**: " + (" ／ ".join(re.sub(r"^\s+- \S+ ", "", l) for l in lines) if lines else "買わない"))
        print()


if __name__ == "__main__":
    main(sys.argv[1])
