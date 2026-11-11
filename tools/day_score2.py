"""レース別シート（買い目カード付き, 2026-10-18 以降の形式）を当日の速報結果で採点する.
買い方ごと（◎厳格・★混戦穴・★フラグ軸・★フラグ点・本線・準本線・穴ワイド）の点数・的中・払戻と、材料ごとの3着内数を出す。
使い方: python3 tools/day_score2.py <レース別シート.md> <results.json（race.netkeiba.com 形式）>"""
import json, re, sys
from collections import defaultdict

CODE = {"新潟": "04", "東京": "05", "京都": "08", "中山": "06", "阪神": "09", "中京": "07", "福島": "03", "小倉": "10", "札幌": "01", "函館": "02"}
SIZE = {"単勝": 1, "複勝": 1, "枠連": 2, "馬連": 2, "ワイド": 2, "馬単": 2, "3連複": 3, "3連単": 3}


def norm(ns, kind):
    return "-".join(ns) if kind in ("馬単", "3連単") else "-".join(sorted(ns, key=int))


def pays(r):
    out = defaultdict(dict)
    for row in r["payouts"]:
        if len(row) < 3 or row[0] not in SIZE:
            continue
        k = row[0]; nums = row[1].split()
        if not nums:
            continue
        ys = [int(y.replace(",", "").replace("円", "")) for y in row[2].split()]
        s = SIZE[k]
        for i, y in enumerate(ys):
            out[k][norm(nums[i * s:(i + 1) * s], k)] = y
    return out


def tickets(body):
    """買い目の文字列 → [(券種, 組)]."""
    out = []
    m = re.search(r"ワイド (\d+)-([\d・]+)（", body)   # ★フラグ点の「ワイド 9-14・5・16・4」
    if m:
        out += [("ワイド", f"{m.group(1)}-{x}") for x in m.group(2).split("・")]
        body = body.replace(m.group(0), "")
    kind = None
    for tok in re.findall(r"単複|単勝|複勝|ワイド|馬連|3連複|\d+(?:-\d+){0,2}", body):
        if tok in ("単複", "単勝", "複勝", "ワイド", "馬連", "3連複"):
            kind = tok; continue
        if kind is None:
            continue
        if kind == "単複":
            out += [("単勝", tok), ("複勝", tok)]; kind = None
        elif kind in ("単勝", "複勝"):
            if "-" not in tok:
                out.append((kind, tok))
            kind = None if kind in ("単勝", "複勝") else kind
        elif tok.count("-") == SIZE[kind] - 1:
            out.append((kind, tok))
    return out


def main(sheet, resf, day_pfx=None):
    res = {r["race_id"]: r for r in json.load(open(resf))}
    txt = open(sheet, encoding="utf-8").read()
    head = re.split(r"\n■ \d+/", txt)[0]
    agg = defaultdict(lambda: [0, 0, 0, []])
    for sec in re.split(r"\n(?=■ )", head):
        m = re.match(r"■ (\S+?)（", sec)
        if not m:
            continue
        kind = m.group(1)
        for l in sec.splitlines()[1:]:
            mm = re.match(r"  - (\S\S)(\d+)R: (.*)（\d+点）$", l)
            if not mm:
                continue
            rid = next((x for x in res if x[4:6] == CODE[mm.group(1)] and int(x[-2:]) == int(mm.group(2))), None)
            if not rid or not any(len(x) > 9 for x in res[rid]["rows"]):
                continue  # まだ結果が出ていないレース
            P = pays(res[rid])
            for k, c in tickets(mm.group(3)):
                y = P.get(k, {}).get(norm(c.split("-"), k), 0)
                a = agg[kind]; a[0] += 1; a[1] += y; a[2] += y > 0
                if y:
                    a[3].append(f"{mm.group(1)}{mm.group(2)}R {k}{c}={y:,}円")
    L = ["| 買い方 | 点数 | 的中 | 払戻 | 回収率 |", "|---|---|---|---|---|"]
    tb = tr = 0
    for k, a in agg.items():
        tb += a[0]; tr += a[1]
        L.append(f"| {k} | {a[0]} | {a[2]} | {a[1]:,}円 | {a[1] / max(a[0] * 100, 1) * 100:.0f}% |")
    L.append(f"| 合計 | {tb} | | {tr:,}円 | {tr / max(tb * 100, 1) * 100:.0f}% |")
    for k, a in agg.items():
        for h in a[3]:
            L.append(f"- {k}: {h}")
    print("\n".join(L))


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2])
