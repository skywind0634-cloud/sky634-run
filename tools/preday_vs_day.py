"""前日（オッズ前・適性だけ）の予想と、当日（オッズ入り）の予想を、実際の結果で比べる（2026-11-07, ユーザー指示
「前日の注目馬と当日変更した予想を検証しろ。適性だけの予想と人気での予想、どちらが的中率が高いか」）.

各版の digest を tools/race_sheet.py に通し、【今日買うもの】の本命枠・少額枠の券を実際の払戻で採点する（1点100円）。
あわせて「★買う」の付いた馬（注目馬）の3着内率も出す。
使い方: python3 tools/preday_vs_day.py <日付> <名前=digestファイル> ... → 標準出力（docs/analysis/preday_vs_day.md に追記用）
"""
import json
import re
import sqlite3
import subprocess
import sys
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CODE = {"札幌": "01", "函館": "02", "福島": "03", "新潟": "04", "東京": "05", "中山": "06", "中京": "07", "京都": "08", "阪神": "09", "小倉": "10"}


def races(date):
    c = sqlite3.connect(ROOT / "data" / "keiba.db")
    out = {}
    for rid, co, no, pay in c.execute("select race_id,course,race_no,payouts from races where date=?", (date,)):
        fin = {n: f for n, f in c.execute("select number,finish from results where race_id=?", (rid,))}
        out[(co, no)] = (json.loads(pay) if pay else {}, fin)
    return out


def pays(p, k):
    return {tuple(sorted(int(x) for x in str(it[0]).replace("-", " ").split())): it[1] for it in p.get(k) or []}


def sheet(path):
    return subprocess.run([sys.executable, str(ROOT / "tools" / "race_sheet.py"), path], capture_output=True, text=True).stdout


def tickets(line):
    m = re.match(r"\s+- (?:（[^）]*）)?(\S\S)(\d+)R (\S+)", line)
    if not m:
        return None
    co, no, key = m.group(1), int(m.group(2)), m.group(3)
    body = line.split(": ", 1)[-1]
    tk = []
    for kind, nums in re.findall(r"(単勝|複勝|ワイド|馬連|3連複) (\d+(?:-\d+)*)", body):
        tk.append((kind, tuple(sorted(int(x) for x in nums.split("-")))))
    if not tk:   # ◆期待値3連複: 1-2-6 / ... の形
        kind = "3連複" if "3連複" in key else "ワイド" if "ワイド" in key else None
        if kind:
            tk = [(kind, tuple(sorted(int(x) for x in t.split("-")))) for t in re.findall(r"\d+(?:-\d+)+", body)]
    return co, no, key, tk


def evaluate(text, R):
    sec = None; res = defaultdict(lambda: [0, 0, 0, 0])   # cost, back, races, races_hit
    bets = []
    for l in text.split("\n"):
        if l.startswith("■ 本命枠"):
            sec = "本命枠"; continue
        if l.startswith("■ 少額枠"):
            sec = "少額枠"; continue
        if l.startswith("【参考") or l.startswith("■ 11/") or l.startswith("■ 10/"):
            sec = None
        if not sec or "超えるので外す" in l:
            continue
        t = tickets(l)
        if not t or (t[0], t[1]) not in R:
            continue
        co, no, key, tk = t
        p, fin = R[(co, no)]
        back = 0
        for kind, h in tk:
            if kind == "単勝":
                back += dict((int(a), b) for a, b in p.get("単勝", [])).get(h[0], 0)
            elif kind == "複勝":
                back += dict((int(a), b) for a, b in p.get("複勝", [])).get(h[0], 0)
            else:
                back += pays(p, kind).get(h, 0)
        r = res[sec]; r[0] += 100 * len(tk); r[1] += back; r[2] += 1; r[3] += back > 0
        bets.append((sec, f"{co}{no}R", key, tk, back))
    return res, bets


def marked(text, R):
    """レース別シートで ★買う の付いた馬の3着内率."""
    n = top3 = 0; race = None
    for l in text.split("\n"):
        m = re.match(r"■ \S+ (\S\S)(\d+)R", l)
        if m:
            race = (m.group(1), int(m.group(2))); continue
        m = re.match(r"\s+(\d+) \S+（.*★買う", l)
        if m and race in R:
            f = R[race][1].get(int(m.group(1)))
            if f:
                n += 1; top3 += f <= 3
    return n, top3


def main(date, *versions):
    R = races(date)
    print(f"## {date}（結果のあるレース {len(R)}）")
    allbets = {}
    for v in versions:
        name, path = v.split("=", 1)
        text = sheet(path)
        res, bets = evaluate(text, R)
        allbets[name] = bets
        n, t3 = marked(text, R)
        line = f"- **{name}**: "
        for sec in ("本命枠", "少額枠"):
            c, b, nr, nh = res[sec]
            if c:
                line += f"{sec} 投資{c:,}円・払戻{b:,}円・収支{b - c:+,}円（回収{b / c:.0%}・{nr}件中{nh}件で的中） ／ "
        line += f"★買うの馬 {n}頭のうち3着内 {t3}頭（{t3 / n:.0%}）" if n else "★買うの馬なし"
        print(line)
    names = list(allbets)
    if len(names) >= 2:
        a, b = names[0], names[-1]
        sa = {(x[1], x[2]): x for x in allbets[a]}; sb = {(x[1], x[2]): x for x in allbets[b]}
        print(f"- {a} にあって {b} で消えた買い目のうち当たったもの: " + ("、".join(f"{k[0]} {k[1]} 払戻{v[4]:,}円" for k, v in sa.items() if k not in sb and v[4]) or "なし"))
        print(f"- {b} で新しく入った買い目のうち当たったもの: " + ("、".join(f"{k[0]} {k[1]} 払戻{v[4]:,}円" for k, v in sb.items() if k not in sa and v[4]) or "なし"))


if __name__ == "__main__":
    main(*sys.argv[1:])
