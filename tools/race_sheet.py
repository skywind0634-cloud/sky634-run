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
         ("◎拾った馬ボックス", "◎拾った馬ボックス", "単勝20倍未満でフラグ点+3以上の上位4頭を軸なしで。ワイドボックス6点＋3連複ボックス4点、5年で回収103%/115%/121%・的中62〜66%"),
         ("◎フラグ点+5", "◎フラグ点+5", "人気を問わずフラグ点+5以上を軸に（2026-11-07 人気の条件を外した）。5年で回収141%/97%/111%・的中34〜37%（ワイド1〜5番人気＋3連複 軸−1〜2−1〜4）"),
         ("★特推し", "★特推し", "★血統穴×専門家/検証済み/開催×血統○/7〜9番人気の走る条件。2024/2025-26で単勝回収127%/160%（ワイド＋3連複は81%/90%）。単勝1点だけ（2026-11-08）"),
         ("◎7・8R", "◎7・8R", "参考（2026-11-07 再検証で7R・8Rの回収80/77/104%に下がり、人気の区切りを外しても100%を超えないので本命枠から外した）。3〜10番人気・フラグ点+4以上を軸に"),
         ("★混戦穴", "★混戦穴", "1番人気4.1倍以上の混戦だけ。人気の順位は問わず単勝50倍未満・フラグ点+3以上を軸に（2026-11-07 変更）。ワイド＋3連複。5年 113%/102%/109%・的中21〜24%"),
         ("★フラグ軸", "★フラグ軸", "人気を問わずフラグ点+4以上を軸に（2026-11-07 人気の条件を外した: 回収114/90/103%・的中31〜34%）ワイド1〜5番人気＋3連複 軸−1〜2−1〜4。5年 142%/104%/120%・的中20〜27%"),
         ("**★フラグ点", "★フラグ点", "1番人気がフラグ点-2以下のとき2〜6番人気の+2以上。単勝115/113/140%・ワイド133/137/195%"),
         ("本線", "本線", "妙味馬の単勝＋馬連。単勝は実オッズで139%/142%、馬連は98%/114%"),
         ("準本線", "準本線", "少額の単複。単勝124%/175%"),
         ("◇大穴ワイド", "◇大穴ワイド", "少額。単勝50倍以上でもフラグ点+4以上の1頭→ワイド1〜3番人気。5年で回収126%/91%/112%・的中4〜5%"),
         ("◎コース血統×フラグ", "◎コース血統×フラグ", "コース別血統○×フラグ+3→+4→1〜3番人気と+4の3連複。未来を見ない2025-26 190%・的中15%"),
         ("◎妙味×フラグ", "◎妙味×フラグ", "1番人気2.5倍以上で妙味条件×フラグ+3→1〜3番人気・+4→1〜3番人気・+3の3連複。2024 470%・2025-26 121%"),
         ("◎フラグ+4ボックス", "◎フラグ+4ボックス", "1番人気2.5倍以上でフラグ点+4以上の3連複ボックス。未来を見ない2025-26 118%・実戦145%"),
         ("◎フラグ+5→+4→人気★", "◎フラグ+5→+4→人気★", "1番人気3.5倍以上で+5→+4→1〜3番人気と+4と★血統穴の3連複（②と同じレースではこの版1つ）。2024 144%・2025-26 125%"),
         ("◎フラグ+5→+4→人気", "◎フラグ+5→+4→人気", "1番人気2.5倍以上で+5→+4→1〜3番人気と+4の3連複。未来を見ない2025-26 121%・的中13%"),
         ("◎人気薄2頭軸", "◎人気薄2頭軸", "1番人気3.5倍以上の混戦で人気薄フラグ上位2頭を2頭軸→1〜3番人気＋フラグ+2以上へ3連複。実オッズ 240/152%・未来を見ない193%"),
         ("◎人気薄フラグ（", "◎人気薄フラグ", "単勝10倍以上・フラグ点+5以上→単勝各100円＋上位3頭のワイドボックス＋2頭×1〜3番人気の3連複。未来を見ない確かめ 2025-26 121%/106%/119%（3連複は+6以上）"),
         ("◎人気薄フラグ×人気ワイド", "◎人気薄フラグ×人気ワイド", "単勝10倍以上・フラグ点+4以上が3頭以上 → 上位5頭から1〜3番人気へワイド。5年 197%/154%/149%・的中レース47%（2026-11-08 総当たり）"),
         ("◇人気薄フラグボックス", "◇人気薄フラグボックス", "別枠・宝くじ型。非根幹距離で単勝10倍以上・フラグ点+4以上が3頭以上→上位6頭までのワイド＋3連複ボックス。5年で投資65,200円・払戻63,790円（2026-11-08 AR杯の反省）"),
         ("穴ワイド", "穴ワイド", "少額。94%/108%（ほぼトントン、高配当の取りこぼし防ぎ）")]


SMALL_CAP = 30  # 少額枠は1日30点まで（2026-10-24 ユーザー「どんだけ金使わせるんだよ」。本線の馬連（最大5点）を戻して15→30）


def _tickets(body):
    return re.findall(r"(単勝 \d+|ワイド \d+-\d+|馬連 \d+-\d+|3連複 \d+-\d+-\d+)", body)


def _split(line):
    title, body = line[4:].split(": ", 1)
    return title, re.sub(r"（\d+点）$", "", body)


# 同じレースに買い方が重なったときの優先順（2026-11-01 京都8Rで3つ重なり32点になった反省。1レース10点は買い方の合計で数える）
PRIO = ["◎フラグ点+5", "◎厳格", "◆期待値3連複", "◆期待値ワイド", "◎拾った馬ボックス", "★特推し"]
RACE_CAP = 10


def cap_per_race(lines):
    """本命枠の行をレースごとにまとめ、優先順に足して1レース10点（重複する買い目は1点）を超える買い方は外す."""
    def key(l):
        return next((i for i, k in enumerate(PRIO) if f" {k}" in l.split(":")[0]), len(PRIO))
    def race(l):
        return re.match(r"  - (\S\S\d+R)", l).group(1)
    def tickets(l):
        body = l.split(": ", 1)[1]
        if "◆期待値" in l.split(":")[0]:
            k = "3連複" if "3連複" in l.split(":")[0] else "ワイド"
            return {(k, x) for x in re.findall(r"\d+-\d+(?:-\d+)?", body)}
        return set(re.findall(r"(単勝|ワイド|馬連|3連複) (\d+(?:-\d+){0,2})", body))
    have, kept = {}, set()
    for i, l in sorted(enumerate(lines), key=lambda x: key(x[1])):
        r = race(l); cur = have.setdefault(r, set()); new = tickets(l) - cur
        if len(cur) + len(new) <= RACE_CAP:
            cur |= new; kept.add(i)
    out = []
    for i, l in enumerate(lines):
        out.append(l if i in kept else l.replace("  - ", "  - （1レース10点を超えるので外す）", 1))
    return [l for l in out if "（1レース10点を超えるので外す）" not in l] + [l for l in out if "（1レース10点を超えるので外す）" in l]


def short_race(title):
    """7R・8R（2026-11-12 ユーザー「7R・8Rはおすすめのレースと穴馬だけ。全部出すのは9R以降」）: 長いレース別シートだけ出さない.
    買い目は外さない（2026-11-12 ユーザー「結果を出せる買い目なら外す必要はない。目的は当てて儲けること。当たる形を外すな」）:
    7R・8Rの確かめた買い方は【今日買うもの】・買い目カードにそのまま残し、7・8Rの馬連ボックス・穴馬の単勝（early.md）も足して買う."""
    m = re.search(r"(\d+)R", title or "")
    return bool(m) and int(m.group(1)) in (7, 8)


LOT_EXTRA = True  # 人気薄フラグ・人気薄2頭軸・人気薄フラグ×人気ワイド・◇人気薄フラグボックスも別枠で買う（2026-11-14 ユーザー「人気薄フラグボックスは外さない。3つに絞る話は3連複フォーメーションの表の4つだけ」）


def buy_list(rows):
    """【今日買うもの】（2026-11-07 改定）: 実戦11日分の買い方ごとの収支（docs/analysis/preday_backtest.md）で、儲かっていた買い方だけを買う.
    本命枠＝◎厳格（11日で +124,390円・的中7/23）。少額枠＝★フラグ軸（+16,700円）→★特推し（+12,170円）→本線（+5,940円）の順（1日30点まで）。
    ◎フラグ点+5（−23,270円・回収44%）・◆期待値・◎拾った馬ボックス・★混戦穴・穴ワイド・◇大穴ワイドは買わない（参考カードには残す）.
    フラグの見直し（選んだ期間とは別のデータでの確認）が終わったら戻すかを決める."""
    out = ["【今日買うもの】（これ以外は買わない）", "■ 本命枠（ふだんの金額。◎厳格だけ）"]
    main = []
    for l in rows["◎厳格"]:
        t, b = _split(l)
        axis, rest = b.split(" → ", 1)
        first = re.match(r"(\d+)", rest.split("単勝 ")[1]).group(1) if "単勝 " in rest else None
        tk = [x for x in _tickets(rest) if first and first in re.findall(r"\d+", x)]
        sel = ([x for x in tk if x.startswith("単勝")][:1] + [x for x in tk if x.startswith("ワイド")][:3]
               + [x for x in tk if x.startswith("馬連")][:1] + [x for x in tk if x.startswith("3連複")][:5])
        main.append(f"  - {t} ◎厳格 軸{first}: " + " / ".join(sel) + f"（{len(sel)}点）")
    out += main or ["  - なし（今日は◎厳格の該当なし）"]
    out.append(f"■ 少額枠（1点100円・1日{SMALL_CAP}点まで。★フラグ軸（ワイド）→★特推し（単勝）→本線の単勝＋馬連の順）")
    small, n = [], 0
    cand = []
    for l in rows["★フラグ軸"]:
        t, b = _split(l)
        ws = re.findall(r"\d+-\d+(?!-)", b.split("／")[0]) if "／" in b else []
        cand.append((t, "★フラグ軸", [f"ワイド {w}" for w in ws[:5]]))
    for l in rows["★特推し"]:
        t, b = _split(l)
        cand.append((t, f"★特推し {b.split(' → ')[0]}", _tickets(b)))
    tan_main = []
    for l in rows["本線"]:
        t, b = _split(l)
        tk = _tickets(b)
        # 2026-11-08: 本線の単勝は上限の外で必ず買う（11/8 福島7R 単勝15 2,020円・福島12R 単勝16 930円・福島8R 単勝6 430円を上限で外した）
        tan_main += [(t, x) for x in tk if x.startswith("単勝")][:1]
        cand.append((t, "本線", [x for x in tk if x.startswith("馬連")][:5]))
    seen = {}
    for t, key, tk in cand:
        # 同じレースで同じ券が既に入っていれば外す（★フラグ軸と◇大穴ワイドの軸が同じ馬のとき等）
        tk = [x for x in tk if x not in seen.get(t, set())]
        if not tk or n + len(tk) > SMALL_CAP:
            continue
        seen.setdefault(t, set()).update(tk)
        n += len(tk)
        small.append(f"  - {t} {key}: " + " / ".join(tk) + f"（{len(tk)}点）")
    for t, x in tan_main:
        if x not in seen.get(t, set()):
            seen.setdefault(t, set()).add(x)
            small.append(f"  - {t} 本線: {x}（1点・上限の外）")
    out += small or ["  - なし"]
    out.append(f"  （少額枠 合計{n}点＋本線の単勝{len(tan_main)}点）")
    # 2026-11-08 ユーザー「こういうのあてろよ。フラグ出ているのに」: 人気薄のフラグ馬同士のボックスは少額枠30点とは別に買う（年に十数レース）
    lot = []
    # 2026-11-08 多角的な総当たりを足したフラグで確かめ直し: ◎人気薄フラグ×人気ワイドは2025-26で91〜97%、◇人気薄フラグボックスは3連複0%に下がったので参考に回し、◎人気薄フラグを買う
    # 2026-11-14 ◎妙味×フラグは買わない（参考カードには残す）: 的中7%・当たりの中央値2,085円（2024）で、最大の当たり1本を抜くと2024の回収が23%（15点まで）。
    # 数本の大当たり頼みで、ユーザー「あまり当たらないなら外す」.
    # 2026-11-14 ユーザー「①は特大馬券を当てるためだから残す」「★版は②とどちらかしか出ないなら残して良い」.
    for kk in ("◎コース血統×フラグ", "◎フラグ+4ボックス", "◎フラグ+5→+4→人気★", "◎フラグ+5→+4→人気"):
        for l in rows[kk]:
            t, b = _split(l)
            ts = re.findall(r"\d+-\d+-\d+", b.split(" → ")[-1])
            lot.append(f"  - {t} {kk}: " + " / ".join(f"3連複 {x}" for x in ts) + f"（{len(ts)}点）")
    # 人気薄の買い方（2026-11-14 ユーザー: 外さない）
    if LOT_EXTRA:
        for l in rows["◎人気薄2頭軸"]:
            t, b = _split(l)
            ts = re.findall(r"\d+-\d+-\d+", b.split(" → ")[-1])
            lot.append(f"  - {t} ◎人気薄2頭軸: " + " / ".join(f"3連複 {x}" for x in ts) + f"（{len(ts)}点）")
        for l in rows["◎人気薄フラグ"]:
            t, b = _split(l)
            tk = _tickets(b.split(" → ")[-1])
            lot.append(f"  - {t} ◎人気薄フラグ: " + " / ".join(tk) + f"（{len(tk)}点）")
        # 2026-11-08 ユーザー「前は当たるのに勝手に指標を変えて当たらないようにするな」: 元のフラグ点（確かめた目盛り）で判定して、どちらも買う
        for l in rows["◎人気薄フラグ×人気ワイド"]:
            t, b = _split(l)
            ws = re.findall(r"(?<![\d-])(\d+-\d+)(?!-)", b.split(" → ")[-1])
            lot.append(f"  - {t} ◎人気薄フラグ×人気ワイド: " + " / ".join(f"ワイド {w}" for w in ws) + f"（{len(ws)}点）")
        for l in rows["◇人気薄フラグボックス"]:
            t, b = _split(l)
            ws = re.findall(r"(?<![\d-])(\d+-\d+)(?!-)", b.split("／")[0]); ts = re.findall(r"\d+-\d+-\d+", b.split("／")[-1])
            tk = [f"ワイド {w}" for w in ws] + [f"3連複 {x}" for x in ts]
            lot.append(f"  - {t} ◇人気薄フラグボックス: " + " / ".join(tk) + f"（{len(tk)}点）")
    # 2026-11-14 ユーザー「各レース40点以内がそもそも多すぎる」: 同じレースで別の買い方と同じ券は1回だけ買う（11/14 京都10R 3連複1-2-13 を2回買っていた）
    seen, dd = {}, []
    for l in lot:
        m = re.match(r"  - (\S+\d+R) (.+?): (.*)（\d+点[^）]*）$", l)
        if not m:
            dd.append(l); continue
        s = seen.setdefault(m.group(1), set())
        tk = [x for x in m.group(3).split(" / ") if x not in s]
        s.update(tk)
        if tk:
            dd.append(f"  - {m.group(1)} {m.group(2)}: " + " / ".join(tk) + f"（{len(tk)}点）")
    lot = dd
    if lot:
        out.append("■ 別枠（1点100円。3連複フォーメーションは①◎フラグ+4ボックス・②◎フラグ+5→+4→人気（1番人気3.5倍以上は★版）・◎コース血統×フラグの3つ（1レース10点まで）＋◎人気薄フラグ・◎人気薄2頭軸・◎人気薄フラグ×人気ワイド・◇人気薄フラグボックス）")
        out += lot
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
        if race is None or short_race(race.split(" ")[1] if " " in race else race):
            return   # 7R・8R のレース別シートは出さない（early.md におすすめの穴馬だけ）
        out.append(f"\n■ {race}")
        out.extend(info)
        out.append("【買う】" + (" ／ ".join(buys) if buys else "なし（このレースは見送り。下は材料）"))
        for b in buys:
            kind = next((k for k in ("◎厳格", "★混戦穴", "★フラグ軸", "◇大穴ワイド", "穴ワイド", "本線", "準本線") if b.startswith(k)), "フラグ点")
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
        for key in ("★特推し", "◎拾った馬ボックス", "◎フラグ点+5", "◎7・8R", "★混戦穴", "★フラグ軸", "◇大穴ワイド", "穴ワイド"):
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
    if "オッズ前" in txt:
        # 2026-11-07 ユーザー指摘「前日と当日の予想が違う」: オッズ前は人気が推定なので、人気・オッズで決まる買い方（◆期待値・◎厳格・
        # ★特推し・本線・◎フラグ点+5 の人気の条件）が当日に入れ替わる。オッズ前の版は軸候補の確認用で、買い目は確定ではないと明示する。
        print("※ オッズ前の仮の版（人気はこちらの推定）。買い目は前売りオッズが入った版（金曜20:40以降の cards-now）か当日朝の版で確定する。"
              "ここでは軸候補・材料の確認用にとどめ、この版の買い目では買わない。\n")
    print(card_summary(path))
    print(txt)


if __name__ == "__main__":
    main(sys.argv[1])
