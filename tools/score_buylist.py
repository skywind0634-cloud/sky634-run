"""【今日買うもの】（tools/race_sheet.py の buy_list）を当日の結果で採点する（2026-10-25）.
使い方: python3 tools/score_buylist.py <レース別シート.md> <results.json> [差し替えファイル.json]
差し替えファイル: {"京都11R": "ワイド 1-3 / 3連複 3-8-10 ..."} のように、レースごとの最終の買い目で置き換える。
"""
import json, re, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))
from day_score2 import CODE, norm, pays  # noqa: E402


def tickets(kind, body):
    if kind.startswith("◆期待値"):
        k = "3連複" if "3連複" in kind else "ワイド"
        return [(k, x) for x in re.findall(r"\d+-\d+(?:-\d+)?", body)]
    return [(k, x) for k, x in re.findall(r"(単勝|ワイド|馬連|3連複) (\d+(?:-\d+){0,2})", body)]


def main(sheet, resf, over=None):
    res = {r["race_id"]: r for r in json.load(open(resf))}
    txt = open(sheet, encoding="utf-8").read().split("【参考")[0]
    ov = json.load(open(over)) if over else {}
    rows, seen = [], set()
    for l in txt.splitlines():
        m = re.match(r"  - (\S\S)(\d+)R (.+?): (.*)", l)
        if not m:
            continue
        race = f"{m.group(1)}{m.group(2)}R"
        frame = "本命枠" if any(k in m.group(3) for k in ("◆", "◎")) else "少額枠"
        if race in ov and frame == "本命枠":
            if race in seen:
                continue
            seen.add(race); tk = tickets("", ov[race]); kind = "差し替え後"
        else:
            tk = tickets(m.group(3), m.group(4)); kind = m.group(3)
        rid = next((x for x in res if x[4:6] == CODE[m.group(1)] and int(x[-2:]) == int(m.group(2))), None)
        P = pays(res[rid]) if rid else {}
        back = [(k, c, P.get(k, {}).get(norm(c.split("-"), k), 0)) for k, c in tk]
        rows.append((frame, race, kind, len(tk), sum(y for *_, y in back), [f"{k}{c}={y:,}円" for k, c, y in back if y]))
    L = ["| 枠 | レース | 買い方 | 点数 | 払戻 | 的中 |", "|---|---|---|---|---|---|"]
    for f, r, k, n, y, h in rows:
        L.append(f"| {f} | {r} | {k} | {n} | {y:,}円 | {'・'.join(h)} |")
    for f in ("本命枠", "少額枠", "合計"):
        sel = [x for x in rows if f == "合計" or x[0] == f]
        n = sum(x[3] for x in sel); y = sum(x[4] for x in sel)
        L.append(f"| **{f}** | | | {n} | {y:,}円 | 投資{n * 100:,}円・収支{y - n * 100:+,}円 |")
    print("\n".join(L))


if __name__ == "__main__":
    main(*sys.argv[1:])
