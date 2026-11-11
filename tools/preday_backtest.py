"""毎週の前日（人気・オッズなし＝適性だけ）と当日（オッズ入り）の予想を、保存してある出馬表から作り直して実際の結果で比べる
（2026-11-07, ユーザー指示「毎週前日に注目馬を出させている。サンプルは2日分ではない」）.

各開催日の当日朝の出馬表（git の履歴。10月は sky634-run）を取り出し、
 - 当日版: そのまま
 - 前日版: 各馬の単勝オッズ・人気と組み合わせオッズを消したもの（前日のオッズ前と同じ条件。枠順は同じ）
の2つで digest → tools/race_sheet.py を作り、【今日買うもの】と「★買う」の馬を実際の結果で採点する。
注意: 実績DB（集計）は今のものを使うので、その日の結果が集計に少し入っている（両方の版に同じだけ入るので比較には影響が小さい）。
使い方: python3 tools/preday_backtest.py → docs/analysis/preday_backtest.md
"""
import datetime as dt
import io
import json
import subprocess
import sys
import tempfile
from contextlib import redirect_stdout
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT)); sys.path.insert(0, str(ROOT / "tools"))
import preday_vs_day as P  # noqa: E402

DAYS = ["2026-10-03", "2026-10-04", "2026-10-10", "2026-10-11", "2026-10-12", "2026-10-17", "2026-10-18",
        "2026-10-24", "2026-10-25", "2026-10-31", "2026-11-01"]


def snapshot(day):
    for ref in ("run/main", "origin/main"):
        c = subprocess.run(["git", "log", ref, "--format=%h", f"--before={day}T04:00:00Z", "-1", "--", f"cards/{day}"],
                           capture_output=True, text=True, cwd=ROOT).stdout.strip()
        if c:
            return c
    return None


def digest_text(day, cards_dir):
    from keiba import analysis, db, digest, pipeline, report
    from keiba.cli import load_params
    from keiba.config import is_target_race
    import keiba.model as M
    from keiba.model import evaluate_race
    M.PARAMS.update(load_params())
    conn = db.connect(); st = analysis.build_stats(conn)
    buf = io.StringIO()
    with redirect_stdout(buf):
        print(digest.GUIDE)
        for c in sorted(pipeline.load_cards(dt.date.fromisoformat(day), cards_dir), key=lambda c: (c.get("course", ""), c.get("race_no", 0))):
            if not c.get("entries") or not is_target_race(c.get("race_no"), c.get("grade"), c.get("surface"), c.get("name")):
                continue
            print(digest.text(c, evaluate_race(c, st, conn, n_sims=0), report.race_title(c)), "\n")
    return buf.getvalue()


def main():
    tot = {k: {s: [0, 0, 0, 0] for s in ("本命枠", "少額枠")} for k in ("前日", "当日")}
    mk = {k: [0, 0] for k in tot}
    lost, gained = [], []
    L = ["# 毎週の前日（適性だけ）と当日（オッズ入り）の予想の比較（tools/preday_backtest.py）", "",
         "当日朝の出馬表から、人気・オッズを消した版（前日と同じ条件）と、そのままの版を作り、同じ方法で【今日買うもの】を出して実際の結果で採点（1点100円）。", "",
         "| 日 | 版 | 本命枠 投資→払戻（的中レース/買ったレース） | 少額枠 投資→払戻 | ★買うの馬 3着内 |", "|---|---|---|---|---|"]
    with tempfile.TemporaryDirectory() as tmp:
        for day in DAYS:
            c = snapshot(day)
            R = P.races(day)
            if not c or not R:
                continue
            base = Path(tmp) / "day" / day; blind = Path(tmp) / "blind" / day
            base.mkdir(parents=True); blind.mkdir(parents=True)
            names = subprocess.run(["git", "ls-tree", "--name-only", c, f"cards/{day}/"], capture_output=True, text=True, cwd=ROOT).stdout.split()
            for n in names:
                raw = subprocess.run(["git", "show", f"{c}:{n}"], capture_output=True, text=True, cwd=ROOT).stdout
                (base / Path(n).name).write_text(raw, encoding="utf-8")
                try:
                    d = json.loads(raw)
                except ValueError:
                    continue
                if isinstance(d, dict) and d.get("entries"):
                    for e in d["entries"]:
                        e["odds"] = None; e["popularity"] = None
                    for k in [k for k in d if "odds" in k.lower()]:
                        d.pop(k)
                    (blind / Path(n).name).write_text(json.dumps(d, ensure_ascii=False), encoding="utf-8")
            bets = {}
            for ver, folder in (("当日", base.parent), ("前日", blind.parent)):
                f = Path(tmp) / f"{ver}_{day}.md"
                f.write_text(digest_text(day, folder), encoding="utf-8")
                text = P.sheet(str(f))
                res, b = P.evaluate(text, R)
                n, t3 = P.marked(text, R)
                bets[ver] = b
                mk[ver][0] += n; mk[ver][1] += t3
                cells = []
                for s in ("本命枠", "少額枠"):
                    x = res[s]; t = tot[ver][s]
                    for i in range(4):
                        t[i] += x[i]
                    cells.append(f"{x[0]:,}→{x[1]:,}円（{x[3]}/{x[2]}）" if x[0] else "-")
                L.append(f"| {day} | {ver} | {cells[0]} | {cells[1]} | {t3}/{n}" + (f"（{t3 / n:.0%}）" if n else "") + " |")
            sa = {(x[1], x[2]) : x for x in bets["前日"]}; sb = {(x[1], x[2]): x for x in bets["当日"]}
            lost += [f"{day} {k[0]} {k[1]} {v[4]:,}円" for k, v in sa.items() if k not in sb and v[4]]
            gained += [f"{day} {k[0]} {k[1]} {v[4]:,}円" for k, v in sb.items() if k not in sa and v[4]]
            print(day, "done", file=sys.stderr)
    L += ["", "## 合計", "", "| 版 | 本命枠 投資→払戻（回収・的中レース率） | 少額枠 投資→払戻（回収・的中率） | ★買うの馬の3着内率 |", "|---|---|---|---|"]
    for ver in ("前日", "当日"):
        cells = []
        for s in ("本命枠", "少額枠"):
            c_, b_, nr, nh = tot[ver][s]
            cells.append(f"{c_:,}→{b_:,}円（{b_ / c_:.0%}・{nh}/{nr}={nh / nr:.0%}）" if c_ else "-")
        n, t3 = mk[ver]
        L.append(f"| {ver} | {cells[0]} | {cells[1]} | {t3}/{n}（{t3 / n:.0%}） |")
    L += ["", "## 当日に入れ替わった買い目で当たったもの", "",
          "- 前日にあって当日に消えた（消して損した）: " + ("、".join(lost) or "なし"),
          "- 当日に新しく入った（入れて得した）: " + ("、".join(gained) or "なし")]
    (ROOT / "docs" / "analysis" / "preday_backtest.md").write_text("\n".join(L) + "\n", encoding="utf-8")
    print("\n".join(L))


if __name__ == "__main__":
    main()
