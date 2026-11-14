"""朝の【今日買うもの】に、前夜の版の買い目を残す（2026-11-14 ユーザー「人気で変える意味がないなら変えないと言ったよね。
下位人気馬で人気順が影響するか？何度目だよ、同じ失敗」。東京10R ★特推し 10トライアンフパスが前夜→朝で8→10人気になって消え、1着）.

ルール:
- 本命枠（◎厳格）は前夜の版のまま（朝に新しく入った軸は足さない）。
- 少額枠・別枠は「前夜の版 ∪ 朝の版」。前夜にあって朝に消えた行を「■ 前夜の版から残す」に全部出す。
  人気・オッズの順位が動いただけでは外さない。
- 外してよいのは取消・除外だけ（朝のカードに馬番が無い馬を含む券は落とす）。馬場の変更は going_check で別に扱う。
使い方: python3 tools/union_night.py <前夜.md> <朝.md> <日付>   （朝.md を上書き）
"""
import glob, json, re, sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
HEAD = "■ 前夜の版から残す（人気・オッズの順位が動いただけでは外さない。取消・除外を含む券だけ落とした）"


def section(t, start, stop):
    i = t.find(start)
    if i < 0:
        return ""
    j = t.find(stop, i + 1)
    return t[i:j if j > 0 else None]


def lines(t, start, stop):
    out = {}
    for l in section(t, start, stop).splitlines():
        m = re.match(r"  - (\S+\d+R) (\S+?)[ :]", l)
        if m:
            out[(m.group(1), m.group(2))] = l
    return out


def runners(day):
    r = {}
    for p in glob.glob(str(ROOT / "cards" / day / "*.json")):
        c = json.load(open(p))
        r[f"{c['course']}{c['race_no']}R"] = {str(e["number"]) for e in c["entries"]}
    return r


def drop_scratched(line, race, run):
    """取消・除外の馬を含む券を落とす. 残りが無ければ None."""
    alive = run.get(race)
    if not alive:
        return line
    head, body = line.split(": ", 1) if ": " in line else (line, "")
    m = re.match(r"\s*\S+\d+R \S+ (\d+)\S*（", head)
    if m and m.group(1) not in alive:      # 軸の馬が取消
        return None
    pts = re.sub(r"（\d+点[^）]*）\s*$", "", body).split(" / ")
    keep = [p for p in pts if all(n in alive for n in re.findall(r"\d+", p.split(" ", 1)[-1]))]
    if not keep:
        return None
    return f"{head}: {' / '.join(keep)}（{len(keep)}点・前夜の版）"


def main(night, morn, day):
    tn = open(night, encoding="utf-8").read()
    tm = open(morn, encoding="utf-8").read()
    if HEAD in tm:
        tm = tm[:tm.find(HEAD)] + tm[tm.find("【参考"):]
    # 本命枠は前夜の版
    hn = section(tn, "■ 本命枠", "■ 少額枠")
    hm = section(tm, "■ 本命枠", "■ 少額枠")
    if hn and hm:
        tm = tm.replace(hm, hn)
    run = runners(day)
    add = []
    for start, stop in (("■ 少額枠", "■ 別枠"), ("■ 別枠", "【参考")):
        n, m = lines(tn, start, stop), lines(tm, start, stop)
        for k, l in n.items():
            if k in m:
                continue
            l2 = drop_scratched(l, k[0], run)
            if l2:
                add.append(l2)
    if add:
        i = tm.find("【参考")
        tm = tm[:i] + HEAD + "\n" + "\n".join(add) + "\n\n" + tm[i:]
    open(morn, "w", encoding="utf-8").write(tm)
    print(f"前夜の版から残した行: {len(add)}")
    for l in add:
        print(l)


if __name__ == "__main__":
    main(*sys.argv[1:])
