"""digest の出力を「レースごと・馬ごと」の1枚にまとめ直す（2026-10-17, ユーザー指摘: 買い目と材料が別々で同じ馬が追えない）.
各レース: 買い目（◎厳格・本線・準本線・フラグ点）→ 名前の出た全馬を人気順に1行ずつ（買う/材料、付いた○×をまとめる）.
使い方: python3 tools/race_sheet.py <digest.txt> → 標準出力
"""
import re, sys
from collections import OrderedDict

SHORT = [("★ 血統の穴", "★血統穴"), ("専門家の見解", "専門家"), ("検証済みの傾向", "検証済み"), ("人気帯の中で走る条件", "走る条件"),
         ("回収率の高い条件", "妙味条件"), ("牝系がこの条件", "牝系"), ("過信禁物の人気馬", "過信禁物(消しではない)"), ("直結コース", "直結コース"),
         ("前走が勝ち馬から", "前走僅差"), ("開催の進み具合", "開催×血統"), ("展開×血統", "展開×血統"), ("展開×上がり能力", "展開×上がり"),
         ("系統×レース条件", "本の検証"), ("種牡馬のクセ", "種牡馬クセ"), ("コース別の種牡馬", "コース別"), ("コース別の血統傾向", "コース別血統"),
         ("最新の種牡馬傾向", "最新種牡馬"), ("★主流", "反主流")]


def main(path):
    out = []
    race = None
    horses = OrderedDict(); buys = []; cat = None; info = []

    def flush():
        if race is None:
            return
        out.append(f"\n■ {race}")
        out.extend(info)
        out.append("【買う】" + (" ／ ".join(buys) if buys else "なし（このレースは見送り。下は材料）"))
        for b in buys:
            kind = "◎厳格" if b.startswith("◎厳格") else "本線" if b.startswith("本線") else "準本線" if b.startswith("準本線") else "フラグ点"
            mm = re.search(r"厳格 (\d+) |単複 (\d+)（|フラグ点: (\d+)", b)
            n = next((int(g) for g in (mm.groups() if mm else []) if g), None)
            if n in horses and kind not in horses[n]["buy"]:
                horses[n]["buy"].append(kind)
        for num, h in sorted(horses.items(), key=lambda x: x[1]["pop"]):
            tags = "・".join(h["tags"])
            buy = " ★買う:" + "+".join(h["buy"]) if h["buy"] else ""
            out.append(f"  {num:>2} {h['name']}（{h['pop']}人気・{h['odds']}倍）{buy}｜{tags}")
    for l in open(path, encoding="utf-8").read().split("\n"):
        if l.startswith("### "):
            flush()
            race = l[4:]; horses = OrderedDict(); buys = []; cat = None; info = []
            continue
        if race is None:
            continue
        m = re.match(r"\s*(?:\*\*)?(?:本線（単複）\s*)?(\d+)\s?(\S+?)（(\d+)人気・([\d.]+)倍", l.replace("**本線（単複） ", "  - ").replace("  - ", ""))
        if l.startswith("  - ◎妙味条件(厳格)"):
            buys.append("◎厳格 " + l.split("）:", 1)[-1].strip()); cat = None; continue
        if l.startswith("  - 本線"):
            buys.append("本線 " + l.split("）:", 1)[-1].strip()); cat = None; continue
        if l.startswith("  - 準本線"):
            buys.append("準本線 " + l.split("）:", 1)[-1].strip()); cat = None; continue
        if l.startswith("**★フラグ点"):
            buys.append(re.sub(r"\*\*", "", l)); cat = None
            mm = re.search(r"(\d+)(\S+?)（(\d+)番人気", l)
            continue
        if l.startswith("- 展開予想") or l.startswith("- 馬場の主流度"):
            info.append("  " + l[2:]); cat = None; continue
        if l.startswith("- "):
            cat = next((v for k, v in SHORT if l[2:].startswith(k)), None)
            continue
        if l.startswith("**本線（単複）"):
            mm = re.search(r"(\d+) (\S+?)（(\d+)人気・([\d.]+)倍", l)
            if mm:
                h = horses.setdefault(int(mm.group(1)), dict(name=mm.group(2), pop=int(mm.group(3)), odds=mm.group(4), tags=[], buy=[]))
                h["buy"].append("本線")
            cat = "本線根拠"; continue
        if cat == "本線根拠" and l.startswith("  - "):
            last = next(reversed(horses.values()))
            last["tags"].append("根拠:" + l[4:].split("（")[0][:40])
            continue
        mm = re.match(r"  - (\d+) (\S+?)（(\d+)人気・([\d.]+)倍", l)
        if cat and mm:
            num = int(mm.group(1))
            h = horses.setdefault(num, dict(name=mm.group(2), pop=int(mm.group(3)), odds=mm.group(4), tags=[], buy=[]))
            body = l.split("：", 1)[1] if "：" in l else ""
            ms = re.findall(r"([◎○▽×▼])（", body) + re.findall(r"）([○▼]) A/E", body) + re.findall(r"最新の傾向 ([○▼])", body)
            marks = "".join(sorted(set(ms), key="◎○▽×▼".index))
            h["tags"].append(cat + marks)
    flush()
    # 買い目に出た馬番を馬に印付け
    txt = "\n".join(out)
    print(txt)


if __name__ == "__main__":
    main(sys.argv[1])
