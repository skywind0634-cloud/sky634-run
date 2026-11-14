"""その日の買い目を、day-results の結果で精算する（2026-11-14 ユーザー「ここまでの結果、検証して」）.
本命枠＝前夜の版（predictions/<土曜>/前夜_<MMDD>.md）の◎厳格、少額枠・別枠＝朝の版（朝_<MMDD>.md）＋前日の軸を残した分（統合_<MMDD>.md）、
1〜8R＝early.md の【買うもの】。終わったレースだけ精算し、投資・払戻・差額を買い方ごとに出す.
使い方: python3 tools/settle_day.py <日付> <結果JSON> [<土曜>]"""
import glob, json, re, sys
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def payouts(rows):
    out = defaultdict(dict)
    for kind, nums, amts, *_ in rows:
        ns = nums.split(); ys = [int(x.replace(",", "").replace("円", "")) for x in amts.split()]
        k = {"単勝": 1, "複勝": 1, "馬連": 2, "ワイド": 2, "3連複": 3, "枠連": 2}.get(kind)
        if not k:
            continue
        for i, y in enumerate(ys):
            combo = ns[i * k:(i + 1) * k]
            out[kind]["-".join(sorted(combo, key=int))] = y
    return out


def tickets(text):
    """文字列 → [(券種, 組)]."""
    tk = []
    for kind, combo in re.findall(r"(単勝|複勝|ワイド|馬連|3連複) (\d+(?:-\d+){0,2})(?![→\d・])", text):
        need = {"単勝": 1, "複勝": 1, "ワイド": 2, "馬連": 2, "3連複": 3}[kind]
        if len(combo.split("-")) == need:
            tk.append((kind, "-".join(sorted(combo.split("-"), key=int))))
    for n, kind in re.findall(r"[◎穴馬 ]+?(\d+)の(単勝|複勝)", text):
        tk.append((kind, n))
    for a, rest in re.findall(r"馬連 (\d+)→([\d・]+)", text):
        tk += [("馬連", "-".join(sorted([a, b], key=int))) for b in rest.split("・")]
    for rest in re.findall(r"馬連ボックス ([\d・]+)", text):
        xs = rest.split("・")
        tk += [("馬連", "-".join(sorted([a, b], key=int))) for i, a in enumerate(xs) for b in xs[i + 1:]]
    return tk


def main(day, res_path, sat=None):
    sat = sat or day
    md = day[5:].replace("-", "")
    P = ROOT / "predictions" / sat
    res = {r["race_id"]: r for r in json.load(open(res_path))}
    rid = {}
    for p in glob.glob(str(ROOT / "cards" / day / "*.json")) + glob.glob(str(ROOT / "cards_early" / day / "*.json")):
        c = json.load(open(p)); rid[f"{c['course']}{c['race_no']}R"] = c["race_id"]
    groups = []   # (枠, 買い方, レース, [券])
    def section(path, start, stop):
        t = open(path, encoding="utf-8").read()
        i = t.find(start); j = t.find(stop, i + 1) if stop else -1
        return t[i:j if j > 0 else None]
    pre = P / f"前夜_{md}.md"
    morn = P / f"朝_{md}.md"
    for l in section(pre if pre.exists() else morn, "■ 本命枠", "■ 少額枠").splitlines():
        m = re.match(r"  - (\S+\d+R) (\S+)", l)
        if m:
            groups.append(("本命枠", m.group(2), m.group(1), tickets(l.split(":", 1)[1])))
    for l in section(morn, "■ 少額枠", "■ 別枠").splitlines():
        m = re.match(r"  - (\S+\d+R) (\S+?)[ :]", l)
        if m:
            groups.append(("少額枠", m.group(2), m.group(1), tickets(l.split(": ", 1)[1])))
    mg = P / f"統合_{md}.md"
    if mg.exists():
        for l in open(mg, encoding="utf-8"):
            m = re.search(r"- (\S+\d+R) (★\S+)", l)
            if m:
                groups.append(("少額枠", m.group(2) + "（前日の軸）", m.group(1), tickets(l.split(": ", 2)[-1])))
    keep_head = "■ 前夜の版から残す"
    if keep_head in open(morn, encoding="utf-8").read():
        for l in section(morn, keep_head, "【参考").splitlines():
            m = re.match(r"  - (\S+\d+R) (\S+?)[ :]", l)
            if m:
                groups.append(("前夜残し", m.group(2), m.group(1), tickets(l.split(": ", 1)[1])))
    for l in section(morn, "■ 別枠", keep_head if keep_head in open(morn, encoding="utf-8").read() else "【参考").splitlines():
        m = re.match(r"  - (\S+\d+R) (\S+?): (.*)", l)
        if m:
            groups.append(("別枠", m.group(2), m.group(1), tickets(m.group(3))))
    em = P / "early.md"
    if em.exists():
        for l in section(em, "【買うもの】", "【面白い").splitlines():
            m = re.match(r"- (\d\d)/(\d\d) (\S+\d+R)（(\S+?)）: .* → (.*)", l)
            if m and f"{m.group(1)}-{m.group(2)}" == day[5:]:
                tx = re.sub(r"（参考[^）]*）", "", m.group(5))
                groups.append(("1〜8R", m.group(4), m.group(3), tickets(tx)))
    agg = defaultdict(lambda: [0, 0, 0, 0])
    lines, pend = [], set()
    for frame, how, race, tk in groups:
        r = res.get(rid.get(race, ""))
        if not r or not r.get("payouts"):
            pend.add(race); continue
        pay = payouts(r["payouts"])
        ret = sum(pay[k].get(c, 0) for k, c in tk)
        bet = 100 * len(tk)
        for key in ((frame, how), (frame, "計"), ("全体", "計")):
            a = agg[key]; a[0] += bet; a[1] += ret; a[2] += 1; a[3] += ret > 0
        if ret:
            hit = [f"{k} {c}" for k, c in tk if pay[k].get(c)]
            lines.append(f"- {race} {frame} {how}: 投資{bet:,}円 → 払戻{ret:,}円（{'・'.join(hit)}）")
    print(f"# {day} の精算（終わったレースだけ。まだ: {len(pend)}レース）\n")
    a = agg[("全体", "計")]
    print(f"**全体: 投資 {a[0]:,}円・払戻 {a[1]:,}円・差額 {a[1] - a[0]:+,}円**\n")
    print("| 枠 | 買い方 | 投資 | 払戻 | 差額 | 当たり/レース |\n|---|---|---|---|---|---|")
    for k in sorted(agg, key=lambda k: (k[0] == "全体", k[0], k[1] != "計", k[1])):
        if k[0] == "全体":
            continue
        a = agg[k]
        print(f"| {k[0]} | {k[1]} | {a[0]:,} | {a[1]:,} | {a[1] - a[0]:+,} | {a[3]}/{a[2]} |")
    print("\n## 当たった券\n")
    print("\n".join(lines) or "- なし")
    if pend:
        print("\n未確定: " + "、".join(sorted(pend)))


if __name__ == "__main__":
    main(*sys.argv[1:])
