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


ORDER = [("◇7R当てにいく", "◇7R当てにいく", "7Rは的中率重視。複勝で的中48〜85%・回収90〜106%（資金を持たせる枠）"),
         ("◆期待値3連複", "◆期待値3連複", "発売中オッズ100〜1000倍の組から上乗せの積1.7以上。2024/2025-26 で127%/415%"),
         ("◆期待値ワイド", "◆期待値ワイド", "オッズ10〜50倍で上乗せの積1.5以上。2024/2025-26 で158%/201%"),
         ("◎妙味条件(厳格)", "◎厳格", "単勝・ワイド・馬連・3連複。実オッズでも 141%/135%（単勝だけなら193%/188%）"),
         ("◎フラグ点+5", "◎フラグ点+5", "人気に関係なく3番人気以下でフラグ点+5以上を軸に。5年で回収256%/148%/141%・的中19〜29%（ワイド1〜5番人気＋3連複 軸−1〜2−1〜4）"),
         ("★特推し", "★特推し", "★血統穴×専門家/検証済み/開催×血統○/7〜9番人気の走る条件。過去1年で3着内A/E 1.40〜1.79・複勝回収103〜121%。ワイド・3連複の相手として"),
         ("◎7・8R", "◎7・8R", "7R・8Rは本命枠。3〜10番人気・フラグ点+4以上を軸に。5年の7R・8Rで回収110%/123%/155%・的中23〜35%（ワイド1〜5番人気＋3連複 軸−1〜2−1〜4）"),
         ("★混戦穴", "★混戦穴", "1番人気4.1倍以上の混戦だけ。ワイド＋3連複。実オッズ5年 186%/120%/138%"),
         ("★フラグ軸", "★フラグ軸", "3番人気以下（上限なし）・フラグ点+4以上を軸にワイド1〜5番人気＋3連複 軸−1〜2−1〜4。5年 142%/104%/120%・的中20〜27%"),
         ("**★フラグ点", "★フラグ点", "1番人気がフラグ点-2以下のとき2〜6番人気の+2以上。単勝115/113/140%・ワイド133/137/195%"),
         ("本線", "本線", "妙味馬の単勝＋馬連。単勝は実オッズで139%/142%、馬連は98%/114%"),
         ("準本線", "準本線", "少額の単複。単勝124%/175%"),
         ("穴ワイド", "穴ワイド", "少額。94%/108%（ほぼトントン、高配当の取りこぼし防ぎ）")]


SMALL_CAP = 30  # 少額枠は1日30点まで（2026-10-24 ユーザー「どんだけ金使わせるんだよ」。本線の馬連（最大5点）を戻して15→30）


def _tickets(body):
    return re.findall(r"(単勝 \d+|ワイド \d+-\d+|馬連 \d+-\d+|3連複 \d+-\d+-\d+)", body)


def _split(line):
    title, body = line[4:].split(": ", 1)
    return title, re.sub(r"（\d+点）$", "", body)


def buy_list(rows):
    """本命枠（◆・◎厳格）と少額枠（本線の単勝＋馬連・★混戦穴/★フラグ軸・穴ワイド、1日30点まで）だけを並べる（2026-10-24）."""
    out = ["【今日買うもの】（これ以外は買わない）", "■ 本命枠（ふだんの金額。◆期待値・◎厳格・★特推し・◎フラグ点+5・◎7・8R。1レース10点まで）"]
    main = []
    for key in ("◆期待値3連複", "◆期待値ワイド"):
        for l in rows[key]:
            t, b = _split(l)
            main.append(f"  - {t} {key}: " + " / ".join(re.findall(r"\d+-\d+(?:-\d+)?", b)))
    for l in rows["◎厳格"]:
        t, b = _split(l)
        axis, rest = b.split(" → ", 1)
        first = re.match(r"(\d+)", rest.split("単勝 ")[1]).group(1) if "単勝 " in rest else None
        tk = [x for x in _tickets(rest) if first and first in re.findall(r"\d+", x)]
        sel = ([x for x in tk if x.startswith("単勝")][:1] + [x for x in tk if x.startswith("ワイド")][:3]
               + [x for x in tk if x.startswith("馬連")][:1] + [x for x in tk if x.startswith("3連複")][:5])
        main.append(f"  - {t} ◎厳格 軸{first}: " + " / ".join(sel) + f"（{len(sel)}点）")
    for l in rows["★特推し"]:
        t, b = _split(l)
        tk = _tickets(b)
        main.append(f"  - {t} ★特推し {b.split(' → ')[0]}: " + " / ".join(tk) + f"（{len(tk)}点）")
    for l in [("◎フラグ点+5", x) for x in rows["◎フラグ点+5"]] + [("◎7・8R", x) for x in rows["◎7・8R"]]:
        key, l = l
        t, b = _split(l)
        ws = re.findall(r"\d+-\d+(?!-)", b.split("／")[0]); ts = re.findall(r"\d+-\d+-\d+", b.split("／")[1]) if "／" in b else []
        main.append(f"  - {t} {key}: " + " / ".join([f"ワイド {w}" for w in ws] + [f"3連複 {x}" for x in ts]) + f"（{len(ws) + len(ts)}点）")
    out += main or ["  - なし（今日は本命枠の該当なし）"]
    out.append(f"■ 少額枠（1点100円・1日{SMALL_CAP}点まで。本線の単勝＋馬連→★混戦穴（ワイド＋3連複）/★フラグ軸（ワイド）→穴ワイドの順）")
    small, n = [], 0
    cand = []
    for l in rows["本線"]:
        t, b = _split(l)
        tk = _tickets(b)
        # 本線は単勝＋馬連（最大5点）（想定2,000円以上の組だけ。10/24 京都12R 馬連2-7 9,930円を外した反省）
        cand.append((t, "本線", [x for x in tk if x.startswith("単勝")][:1] + [x for x in tk if x.startswith("馬連")][:5]))
    for key in ("★混戦穴", "★フラグ軸"):
        for l in rows[key]:
            t, b = _split(l)
            ws = re.findall(r"\d+-\d+(?!-)", b.split("／")[0]) if "／" in b else []
            # 2026-10-27 紐の検証（docs/analysis/himo_width_check.md）: ★混戦穴はワイドだけだと2024が73%で、3連複を足すと185/120/136%
            # → ワイド＋3連複（10点）。★フラグ軸はワイド1〜5番人気だけ（108/124/115%・的中20〜27%）
            ts = re.findall(r"\d+-\d+-\d+", b.split("／")[1]) if key == "★混戦穴" and "／" in b else []
            cand.append((t, key, [f"ワイド {w}" for w in ws[:5]] + [f"3連複 {x}" for x in ts]))
    for l in rows["穴ワイド"]:
        t, b = _split(l)
        first = b.split(" / ")[0]
        ws = re.findall(r"\d+-\d+", first)[:2]
        cand.append((t, "穴ワイド", [f"ワイド {w}" for w in ws]))
    for t, key, tk in cand:
        if not tk or n + len(tk) > SMALL_CAP:
            continue
        n += len(tk)
        small.append(f"  - {t} {key}: " + " / ".join(tk) + f"（{len(tk)}点）")
    out += small or ["  - なし"]
    out.append(f"  （少額枠 合計{n}点）")
    return out


def card_summary(path):
    """買い目カードを、買い方ごと（強い順）に全レース分まとめる."""
    txt = open(path, encoding="utf-8").read()
    rows = {k: [] for _, k, _ in ORDER}
    for b in re.split(r"\n(?=### )", txt):
        if not b.startswith("### "):
            continue
        title = re.sub(r"^\S+ ", "", b.splitlines()[0][4:]).split(" ")[0]
        for l in b.splitlines():
            t = l.strip().lstrip("- ").strip()
            for pre, key, _ in ORDER:
                if t.startswith(pre) and not t.startswith(("本線の買い目", "本線（単勝）", "本線: なし")):
                    body = t.split("）: ", 1)[-1] if "）: " in t else t.split("** → ", 1)[-1]
                    pts = len(re.findall(r"\d+-\d+(?:-\d+)?", body)) + len(re.findall(r"単勝 \d+", body)) + 2 * len(re.findall(r"単複 \d+", body))
                    rows[key].append(f"  - {title}: {body}（{pts}点）")
                    break
    out = buy_list(rows) + ["", "【参考: 全部の買い方のカード（買うのは上の【今日買うもの】だけ。取りこぼしの確認用）】"]
    for _, key, note in ORDER:
        out.append(f"■ {key}（{note}）")
        out += rows[key] or ["  - 該当なし"]
    return "\n".join(out)


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
            kind = next((k for k in ("◎厳格", "★混戦穴", "★フラグ軸", "穴ワイド", "本線", "準本線") if b.startswith(k)), "フラグ点")
            if kind == "フラグ点":
                ns = [int(x) for x in re.findall(r"単勝 (\d+)", b)] or [int(x) for x in re.findall(r"フラグ点: (\d+)\D", b) if "番人気" not in b.split("フラグ点: ")[1][:6]]
            elif kind == "穴ワイド":
                ns = [int(x) for x in re.findall(r"(?:^穴ワイド |/ )(\d+)\D", b)]
            else:
                mm = re.search(r"厳格 (\d+) |単複 (\d+)（|フラグ点: (\d+)|軸 (\d+)", b)
                ns = [next((int(g) for g in (mm.groups() if mm else []) if g), None)]
            for n in ns:
                if n not in horses:
                    continue
                if kind not in horses[n]["buy"]:
                    horses[n]["buy"].append(kind)
        for num, h in sorted(horses.items(), key=lambda x: x[1]["pop"]):
            tags = "・".join(h["tags"])
            buy = " ★買う:" + "+".join(h["buy"]) if h["buy"] else ""
            out.append(f"  {num:>2} {h['name']}（{h['pop']}人気・{h['odds'] if h['odds'] == 'オッズ前' else h['odds'] + '倍'}）{buy}｜{tags}")
    for l in open(path, encoding="utf-8").read().split("\n"):
        if l.startswith("### "):
            flush()
            race = l[4:]; horses = OrderedDict(); buys = []; cat = None; info = []
            continue
        if race is None:
            continue
        m = re.match(r"\s*(?:\*\*)?(?:本線（単勝）\s*)?(\d+)\s?(\S+?)（(\d+)人気・([\d.]+)倍", l.replace("**本線（単勝） ", "  - ").replace("  - ", ""))
        if l.startswith("  - ◎妙味条件(厳格)"):
            buys.append("◎厳格 " + l.split("）:", 1)[-1].strip()); cat = None; continue
        for key in ("★特推し", "◎フラグ点+5", "◎7・8R", "★混戦穴", "★フラグ軸", "穴ワイド"):
            if l.startswith("  - " + key):
                buys.append(key + " " + l.split("）: ", 1)[-1].strip()); cat = None
                break
        else:
            key = None
        if key:
            continue
        if l.startswith("レースの形"):
            info.append("  " + l); continue
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
        if l.startswith("**本線（単勝）"):
            mm = re.search(r"(\d+) (\S+?)（(?:想定)?(\d+)(?:人気|番手)・([\d.]+倍|オッズ前)", l)
            if mm:
                h = horses.setdefault(int(mm.group(1)), dict(name=mm.group(2), pop=int(mm.group(3)), odds=mm.group(4).replace("倍", ""), tags=[], buy=[]))
                h["buy"].append("本線")
            cat = "本線根拠"; continue
        if cat == "本線根拠" and l.startswith("  - "):
            last = next(reversed(horses.values()))
            last["tags"].append("根拠:" + l[4:].split("（")[0][:40])
            continue
        mm = re.match(r"  - (\d+) (\S+?)（(?:想定)?(\d+)(?:人気|番手)・([\d.]+倍|オッズ前)", l)
        if cat and mm:
            num = int(mm.group(1))
            h = horses.setdefault(num, dict(name=mm.group(2), pop=int(mm.group(3)), odds=mm.group(4).replace("倍", ""), tags=[], buy=[]))
            body = l.split("：", 1)[1] if "：" in l else ""
            ms = re.findall(r"([◎○▽×▼])（", body) + re.findall(r"）([○▼]) A/E", body) + re.findall(r"最新の傾向 ([○▼])", body)
            marks = "".join(sorted(set(ms), key="◎○▽×▼".index))
            h["tags"].append(cat + marks)
    flush()
    # 買い目に出た馬番を馬に印付け
    txt = "\n".join(out)
    print(card_summary(path))
    print(txt)


if __name__ == "__main__":
    main(sys.argv[1])
