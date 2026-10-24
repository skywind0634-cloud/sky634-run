"""朝の買い目を基本に、当日の馬場発表で「朝の予想のままでよいか」を確かめる（2026-10-24, ユーザー「朝の予想を基本に、途中で馬場を見て当初の予想でよいか検証することも大事」）.
レースごとに、朝の馬場（朝のカード）と今の馬場（最新のカード）を比べ、
- 同じ → 「朝のまま」
- 変わった → 朝のオッズ・人気のまま馬場だけ今の発表に替えて作った【今日買うもの】と朝の分の差（オッズ・人気の変化では買い目を変えない）（追加・外す）と、馬場で付いた／消えた材料（種牡馬×馬場・ダート道悪など）を出す。
使い方: python3 tools/going_check.py <日付> <朝のカードのコミット>（例: git の朝の版）
"""
import datetime as dt, json, re, subprocess, sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT)); sys.path.insert(0, str(ROOT / "tools"))
from keiba import analysis, db, digest, pipeline, report  # noqa: E402
from keiba.config import is_target_race  # noqa: E402
from keiba.model import evaluate_race  # noqa: E402
import keiba.model as M  # noqa: E402
from keiba.cli import load_params  # noqa: E402
from going_scenarios import buy_lines  # noqa: E402

GOING_WORDS = ("稍重", "重・不良", "不良", "道悪", "時計がかかる", "反主流")


def _git_json(rev, path):
    try:
        return json.loads(subprocess.run(["git", "show", f"{rev}:{path}"], cwd=ROOT, capture_output=True, text=True, check=True).stdout)
    except (subprocess.CalledProcessError, ValueError):
        return None


def morning_card(day, rev, name):
    """朝の版のカード（朝のオッズ・人気のまま）。馬場だけを今の発表に替えて比べるため（オッズ・人気の変化では買い目を変えない）."""
    c = _git_json(rev, f"cards/{day}/{name}")
    if c:
        o = _git_json(rev, f"cards/{day}/odds/{name}")
        if o:
            c["_odds"] = o
    return c


def going_notes(txt):
    return sorted({re.sub(r"（.*", "", l.split("：", 1)[-1])[:70] + f"［{l.split('（')[0].strip(' -')}］"
                   for l in txt.splitlines() if l.startswith("  - ") and "：" in l and any(w in l for w in GOING_WORDS)})


def main(day, rev):
    M.PARAMS.update(load_params())
    conn = db.connect(); st = analysis.build_stats(conn)
    folder = ROOT / "cards" / day
    print(f"# 馬場の確認 {day}（朝の買い目を基本に、今の馬場で見直す）\n")
    for c in sorted(pipeline.load_cards(dt.date.fromisoformat(day)), key=lambda c: (c.get("course", ""), c.get("race_no", 0))):
        if not c.get("entries") or not is_target_race(c.get("race_no"), c.get("grade"), c.get("surface"), c.get("name")):
            continue
        name = next((p.name for p in folder.glob("*.json") if json.loads(p.read_text()).get("race_no") == c["race_no"] and json.loads(p.read_text()).get("course") == c["course"]), None)
        if not c.get("going"):
            print(f"## {c['course']}{c['race_no']}R: 今の馬場の発表が取れない（発走後など）… 朝のまま\n"); continue
        c0 = morning_card(day, rev, name) or c   # 朝のオッズ・人気で固定し、馬場だけ替える
        g0, g1 = c0.get("going") or "良", c["going"]
        head = f"## {c['course']}{c['race_no']}R {c.get('surface')}{c.get('distance')}: 朝 {g0} → 今 {g1}"
        grp = lambda g: "良" if g.startswith("良") else "稍重" if g.startswith("稍") else "重" if g.startswith("重") else "不良"
        if grp(g0) == grp(g1):
            print(head + " … **朝のままでよい**\n"); continue
        txts = {}
        for g in (g0, g1):
            cc = dict(c0); cc["going"] = g
            txts[g] = digest.text(cc, evaluate_race(cc, st, conn, n_sims=0), report.race_title(cc))
        b0, b1 = set(buy_lines(txts[g0])), set(buy_lines(txts[g1]))
        print(head + (" … 買い目は朝のままでよい（材料は変わる）" if b0 == b1 else " … **買い目を見直す**"))
        for l in sorted(b1 - b0):
            print(f"- 追加: {l.strip(' -')}")
        for l in sorted(b0 - b1):
            print(f"- 外す: {l.strip(' -')}")
        n0, n1 = set(going_notes(txts[g0])), set(going_notes(txts[g1]))
        for l in sorted(n1 - n0):
            print(f"  - 今の馬場で付いた材料: {l}")
        for l in sorted(n0 - n1):
            print(f"  - 今の馬場で消えた材料: {l}")
        print()


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2])
