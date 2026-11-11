"""前日（適性だけ）の軸を当日も外さない（2026-11-07, ユーザー「根拠があるなら人気を考慮してよいが、根拠がないのに5番人気になったから
切る、はするな」）.
前日版（オッズ前）の適性の買い方（◎フラグ点+5・★フラグ軸・穴ワイド）の軸の馬が、当日版で同じ買い方の軸から外れていたら、
その馬を軸に当日の人気で紐を組み直して足す（◎フラグ点+5・★フラグ軸＝ワイド→1〜5番人気＋3連複 軸−1〜2−1〜4番人気、
穴ワイド＝ワイド→1・2番人気）。同じレースで同じ券は重ねない。オッズで値打ちを判断する買い方は当日版のまま。
使い方: python3 tools/merge_preday.py <前日版のレース別シート> <当日版のレース別シート>
"""
import re
import sys

APT = ("★フラグ軸",)   # 2026-11-07: 買うのは★フラグ軸だけになったので、前日の軸を残すのも★フラグ軸だけ


def axes(text):
    """レース別シートの各レースの【買う】行から、買い方ごとの軸の馬番。あわせて当日の人気→馬番."""
    out, pops, race = {}, {}, None
    for l in text.split("\n"):
        m = re.match(r"■ \S+ (\S\S\d+R)", l)
        if m:
            race = m.group(1); continue
        if race and l.startswith("【買う】"):
            for part in l[4:].split(" ／ "):
                for key in APT:
                    mm = re.match(rf"{re.escape(key)} (?:軸 )?(\d+)", part.strip())
                    if mm:
                        out.setdefault(race, {}).setdefault(key, set()).add(int(mm.group(1)))
        mm = re.match(r"\s+(\d+) \S+?（(\d+)人気", l)
        if race and mm:
            pops.setdefault(race, {})[int(mm.group(2))] = int(mm.group(1))
    return out, pops


def bought(text):
    have, sec = {}, None
    for l in text.split("\n"):
        if l.startswith("【参考"):
            break
        m = re.match(r"\s+- (\S\S\d+R) ", l)
        if m and "超えるので外す" not in l:
            have.setdefault(m.group(1), set()).update(re.findall(r"(?:単勝|複勝|ワイド|馬連|3連複) \d+(?:-\d+)*", l))
    return have


def merge(pre_text, day_text):
    pre, _ = axes(pre_text)
    day, pops = axes(day_text)
    have = bought(day_text)
    added = []
    for race, d in pre.items():
        pop = pops.get(race, {})
        for key, nums in d.items():
            for a in nums:
                if a in day.get(race, {}).get(key, set()):
                    continue
                p = {r: n for r, n in pop.items() if n != a}
                if key == "穴ワイド":
                    tk = [f"ワイド {'-'.join(map(str, sorted((a, p[r]))))}" for r in (1, 2) if r in p]
                else:
                    tk = [f"ワイド {'-'.join(map(str, sorted((a, p[r]))))}" for r in range(1, 6) if r in p]
                    tk += sorted({f"3連複 {'-'.join(map(str, sorted((a, p[x], p[y]))))}" for x in (1, 2) for y in range(1, 5) if x != y and x in p and y in p})
                tk = [t for t in tk if t not in have.get(race, set())]
                if not tk:
                    continue
                have.setdefault(race, set()).update(tk)
                sec = "本命枠" if key == "◎フラグ点+5" else "少額枠"
                added.append((sec, f"  - {race} {key}（前日の軸 {a} を当日も残す）: " + " / ".join(tk) + f"（{len(tk)}点）"))
    return added


def main(pre_path, day_path):
    added = merge(open(pre_path, encoding="utf-8").read(), open(day_path, encoding="utf-8").read())
    print("【前日の適性の軸で、当日の版から外れたもの（当日の人気で紐を組み直して買う）】")
    for sec, l in added:
        print(f"{sec}: {l.strip()}")
    if not added:
        print("  - なし")


if __name__ == "__main__":
    main(*sys.argv[1:])
