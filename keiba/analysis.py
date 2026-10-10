"""実績データ(data/keiba.db)からの多角的集計.

全ての集計は『出走数 n / 勝利 w / 3着内 t』で持ち、予想時は階層的な経験ベイズ縮約で
    種牡馬 → 系統 → 全体平均
の順に事前分布へ引き寄せる。出走数が少ない条件での過大評価を防ぐため。
"""
from __future__ import annotations

import json
import math
from collections import Counter, defaultdict
from dataclasses import dataclass, field

from .config import distance_band, going_group
from . import factors as F
from . import knowledge as K
from .racing import dist_change, style_from_passing


@dataclass
class Cell:
    n: int = 0
    w: int = 0
    t: int = 0
    roi_sum: float = 0.0  # 単勝回収(払戻合計, 100円単位)

    def add(self, finish: int | None, odds: float | None):
        self.n += 1
        if finish == 1:
            self.w += 1
            if odds:
                self.roi_sum += odds
        if finish is not None and finish <= 3:
            self.t += 1

    @property
    def win_rate(self):
        return self.w / self.n if self.n else 0.0

    @property
    def top3_rate(self):
        return self.t / self.n if self.n else 0.0

    @property
    def roi(self):
        return self.roi_sum / self.n if self.n else 0.0


@dataclass
class Stats:
    cells: dict = field(default_factory=lambda: defaultdict(Cell))
    base_top3: float = 0.0
    base_win: float = 0.0
    n_races: int = 0
    pace_freq: dict = field(default_factory=lambda: defaultdict(Counter))   # (場,芝ダ,距離) → ラップ分類の頻度
    sire_style: dict = field(default_factory=lambda: defaultdict(Counter))  # 父 → 産駒の脚質分布
    standards: dict = field(default_factory=dict)  # (場,芝ダ,距離,良/道悪) → (平均タイム, 標準偏差)

    def get(self, *key) -> Cell:
        return self.cells.get(key, Cell())

    def shrunk_top3(self, key: tuple, prior: float, k: float = 20.0) -> float:
        c = self.get(*key)
        return (c.t + k * prior) / (c.n + k)

    def hier_top3(self, keys: list[tuple], k: float = 20.0) -> tuple[float, int]:
        """keys は [最も粗い, ..., 最も細かい]. 粗い方から順に縮約を掛けていく."""
        p = self.base_top3 or 0.21
        n_last = 0
        for key in keys:
            p = self.shrunk_top3(key, p, k)
            n_last = self.get(*key).n
        return p, n_last

    def log_ratio(self, keys: list[tuple], k: float = 20.0) -> tuple[float, int]:
        p, n = self.hier_top3(keys, k)
        base = self.base_top3 or 0.21
        return math.log(max(p, 1e-4) / base), n


def draw_group(gate: int | None) -> str:
    if not gate:
        return "?"
    return "内" if gate <= 3 else ("中" if gate <= 6 else "外")


def build_stats(conn, before: str | None = None) -> Stats:
    """before (YYYY-MM-DD) を指定するとその日より前のレースだけで集計（バックテスト用）."""
    st = Stats()
    rows = conn.execute("""
        SELECT r.*, ra.course, ra.surface, ra.distance, ra.going, ra.pace_type, ra.grade, ra.date,
               ra.n_runners, ra.direction,
               h.sire, h.damsire, h.dam, h.sire_line, h.damsire_line, h.family
        FROM results r
        JOIN races ra ON ra.race_id = r.race_id
        LEFT JOIN horses h ON h.horse_id = r.horse_id
        WHERE ra.surface IN ('芝','ダ') AND (? IS NULL OR ra.date < ?)
        ORDER BY r.horse_id, ra.date
    """, (before, before)).fetchall()
    # レース内の上がり3F順位
    by_race: dict[str, list] = defaultdict(list)
    for r in rows:
        if r["last3f"]:
            by_race[r["race_id"]].append(r["last3f"])
    for v in by_race.values():
        v.sort()
    # 基準タイム（場×芝ダ×距離×良/道悪 の完走馬の平均と標準偏差）
    times: dict[tuple, list] = defaultdict(list)
    for r in rows:
        if r["time_sec"] and r["finish"]:
            times[(r["course"], r["surface"], r["distance"], going_group(r["going"]))].append(r["time_sec"])
    for k, v in times.items():
        if len(v) >= 30:
            m = sum(v) / len(v)
            sd = (sum((x - m) ** 2 for x in v) / len(v)) ** 0.5
            st.standards[k] = (m, sd)
    # インブリード（馬ごとに一度だけ判定）
    crosses: dict[str, list] = {}
    for h in conn.execute("SELECT horse_id, pedigree FROM horses WHERE pedigree IS NOT NULL"):
        try:
            ped = json.loads(h["pedigree"])
        except (TypeError, ValueError):
            continue
        from . import tailfemale as TF
        xs = TF.crosses(h["horse_id"])     # 5代血統表から計算済みならそれを使う
        crosses[h["horse_id"]] = [n for n, g in (xs if xs is not None else K.detect_crosses(ped))
                                  if sum(int(x) for x in g.split("×")) <= 9]  # 4×5 以内
    tot = Cell()
    races = set()
    prev = None          # 同一馬の前走行
    hist: list = []      # 同一馬の過去走（コース実績用）
    last_rest_date = {}  # 休み明け走の日付（叩き2戦目判定）
    for r in rows:
        f, o = r["finish"], r["odds"]
        s, band, gg = r["surface"], distance_band(r["distance"] or 0), going_group(r["going"])
        if prev is None or prev["horse_id"] != r["horse_id"]:
            prev, hist = None, []
        # 前走からの距離変化・間隔・クラス・騎手・斤量（同一馬の時系列）
        chg = dist_change(prev["distance"] if prev else None, r["distance"])
        days = F.days_between(prev["date"], r["date"]) if prev else None
        ib = F.interval_bucket(days)
        second = False
        if prev and ib in ("中1週", "中2-4週", "中5-8週"):
            second = last_rest_date.get(r["horse_id"]) == prev["date"]
        if ib in ("休み明け", "長期休養明け"):
            last_rest_date[r["horse_id"]] = r["date"]
        cls = F.class_bucket(prev["grade"] if prev else None, r["grade"])
        jchg = F.jockey_bucket(prev["jockey"] if prev else None, r["jockey"])
        cchg = F.carried_bucket(prev["weight_carried"] if prev else None, r["weight_carried"])
        cexp = F.course_exp_bucket([dict(h) for h in hist], r["course"], s) if hist else None
        season = F.season_of(r["date"])
        hc = crosses.get(r["horse_id"])
        style, _esi = style_from_passing(r["passing"], r["n_runners"])
        agari_top = None
        if r["last3f"] and by_race.get(r["race_id"]):
            agari_top = "上がり上位" if by_race[r["race_id"]].index(r["last3f"]) < 3 else "上がり下位"
        cs = (r["course"], s, r["distance"])
        if r["race_id"] not in races:
            races.add(r["race_id"])
            if r["pace_type"]:
                st.pace_freq[cs][r["pace_type"]] += 1
        tot.add(f, o)
        if style and r["sire"]:
            st.sire_style[r["sire"]][style] += 1
        keys = [
            ("sire", r["sire"], s, band),
            ("sire_s", r["sire"], s),
            ("sire_cs", r["sire"], r["course"], s, band),
            ("sire_dist", r["sire"], s, r["distance"]),
            ("sire_going", r["sire"], s, gg),
            ("sire_pace", r["sire"], r["pace_type"]),
            ("sire_dchg", r["sire"], s, chg),
            ("line", r["sire_line"], s, band),
            ("line_s", r["sire_line"], s),
            ("line_cs", r["sire_line"], r["course"], s),
            ("line_going", r["sire_line"], s, gg),
            ("line_pace", r["sire_line"], r["pace_type"]),
            ("line_dchg", r["sire_line"], s, chg),
            ("damsire", r["damsire"], s, band),
            ("dsline", r["damsire_line"], s, band),
            ("nick", r["sire"], r["damsire_line"]),
            ("nickline", r["sire_line"], r["damsire_line"]),
            ("dam", r["dam"]),
            ("family", r["family"]),
            ("jockey", r["jockey"]),
            ("jockey_cs", r["jockey"], r["course"], s),
            ("jockey_style", r["jockey"], style),
            ("trainer", r["trainer"]),
            ("jt", r["jockey"], r["trainer"]),
            ("draw", *cs, draw_group(r["gate"])),
            ("draw_all", *cs),
            ("style_bias", *cs, style),
            ("style_bias_all", *cs),
            ("style_pace", style, r["pace_type"]),
            ("style_going", s, gg, style),
            ("agari_cs", r["course"], s, band, agari_top),
            ("dchg", s, band, chg),
            # ---- その他の要因
            ("interval", s, ib),
            ("trainer_rest", r["trainer"], "休み明け") if ib in ("休み明け", "長期休養明け") else (None,),
            ("second_after_rest", s) if second else (None,),
            ("class_chg", s, cls),
            ("jockey_chg", jchg),
            ("carried_chg", s, cchg),
            ("body_chg", F.body_bucket(r["body_weight_diff"])),
            ("course_exp", r["course"], s, cexp),
            ("sex_season", r["sex"], season, s),
            ("age_season", F.age_group(r["age"]), season, s),
            ("sire_season", r["sire"], season, s),
            ("style_field", style, F.field_size_bucket(r["n_runners"])),
            ("debut", s) if prev is None else (None,),
            ("sire_debut", r["sire"], s) if prev is None else (None,),
            ("trainer_debut", r["trainer"]) if prev is None else (None,),
            ("has_cross", s, bool(hc)) if hc is not None else (None,),
            ("popularity", r["popularity"]),
        ]
        ca = K.course_attrs(r["course"], s, r["distance"])
        keys += [("sire_straight", r["sire"], s, ca["straight_cat"]), ("sire_slope", r["sire"], s, ca["slope"]),
                 ("sire_turn", r["sire"], s, ca["turn"]), ("sire_field", r["sire"], F.field_size_bucket(r["n_runners"])),
                 ("line_straight", r["sire_line"], s, ca["straight_cat"]), ("line_slope", r["sire_line"], s, ca["slope"]),
                 ("attr_style", s, ca["straight_cat"], ca["slope"], style)]
        if ib in ("休み明け", "長期休養明け"):
            keys.append(("sire_rest", r["sire"], True))
        keys += [("cross", name, s) for name in (hc or [])]
        for k in keys:
            if None in k:
                continue
            st.cells[k].add(f, o)
        prev = r
        hist.append(r)
    st.base_top3 = tot.top3_rate
    st.base_win = tot.win_rate
    st.n_races = len(races)
    return st


def horse_history(conn, horse_id: str, before_date: str | None = None, limit: int = 10) -> list[dict]:
    q = """
        SELECT r.*, ra.date, ra.course, ra.surface, ra.distance, ra.going, ra.grade, ra.n_runners,
               ra.pace_type, ra.last3f AS race_last3f, ra.direction,
               r.time_sec - (SELECT MIN(r3.time_sec) FROM results r3
                              WHERE r3.race_id = r.race_id AND r3.finish = 1) AS behind,
               CASE WHEN r.last3f IS NULL THEN NULL ELSE
                 (SELECT COUNT(*) + 1 FROM results r2
                   WHERE r2.race_id = r.race_id AND r2.last3f < r.last3f) END AS last3f_rank
        FROM results r JOIN races ra ON ra.race_id = r.race_id
        WHERE r.horse_id = ? AND ra.surface IN ('芝','ダ') {cond}
        ORDER BY ra.date DESC LIMIT ?
    """.format(cond="AND ra.date < ?" if before_date else "")
    args = [horse_id] + ([before_date] if before_date else []) + [limit]
    return [dict(r) for r in conn.execute(q, args).fetchall()]


# ---------------------------------------------------------------- summary report

def top_table(st: Stats, prefix: str, fixed: tuple, min_n: int = 30, n: int = 15, sort="top3"):
    """prefix で始まり、残りのキーが fixed に一致するセルを成績順に並べる."""
    out = []
    for key, c in st.cells.items():
        if key[0] != prefix or c.n < min_n:
            continue
        if key[2:2 + len(fixed)] != fixed:
            continue
        out.append((key[1], c))
    keyf = {"top3": lambda x: x[1].top3_rate, "win": lambda x: x[1].win_rate, "roi": lambda x: x[1].roi}[sort]
    out.sort(key=keyf, reverse=True)
    return out[:n]


def summary_markdown(st: Stats) -> str:
    lines = ["# 血統データベース 集計サマリー（自動生成）", "",
             f"- 集計レース数: {st.n_races}", f"- 全体 勝率 {st.base_win:.1%} / 複勝率 {st.base_top3:.1%}", ""]
    if st.n_races == 0:
        lines.append("※ まだ実績データが取り込まれていません。`python -m keiba.cli update-results` を実行してください。")
        return "\n".join(lines)

    def tbl(title, rows):
        lines.extend([f"## {title}", "", "| 名前 | 出走 | 勝率 | 複勝率 | 単回収 |", "|---|---:|---:|---:|---:|"])
        for name, c in rows:
            lines.append(f"| {name} | {c.n} | {c.win_rate:.1%} | {c.top3_rate:.1%} | {c.roi*100:.0f}% |")
        lines.append("")

    for s in ("芝", "ダ"):
        for band, label in (("sprint", "短距離"), ("mile", "マイル"), ("middle", "中距離"), ("long", "長距離")):
            tbl(f"種牡馬 {s}{label} 複勝率上位", top_table(st, "sire", (s, band)))
        tbl(f"種牡馬 {s} 道悪(稍重〜不良) 複勝率上位", top_table(st, "sire_going", (s, "soft"), min_n=20))
    for pace in ("瞬発", "持続", "消耗"):
        tbl(f"系統別 {pace}戦 複勝率", top_table(st, "line_pace", (pace,), min_n=30))
    tbl("母父 芝中距離 複勝率上位", top_table(st, "damsire", ("芝", "middle")))
    tbl("母父 ダート中距離 複勝率上位", top_table(st, "damsire", ("ダ", "middle")))
    nick = [((k[1], k[2]), c) for k, c in st.cells.items() if k[0] == "nick" and c.n >= 30]
    nick.sort(key=lambda x: x[1].top3_rate, reverse=True)
    tbl("実測ニックス（父×母父系統）複勝率上位", [(f"{a} × {b}", c) for (a, b), c in nick[:20]])
    # ---- 距離
    for s_ in ("芝", "ダ"):
        for band, label in (("sprint", "短距離"), ("mile", "マイル"), ("middle", "中距離"), ("long", "長距離")):
            rows = [(chg, st.get("dchg", s_, band, chg)) for chg in ("延長", "同", "短縮")]
            tbl(f"距離変化別 {s_}{label}（前走からの延長/同距離/短縮）", [(a, c) for a, c in rows if c.n])
    for chg in ("延長", "短縮"):
        for s_ in ("芝", "ダ"):
            tbl(f"系統別 {s_} 距離{chg}時 複勝率上位", top_table(st, "line_dchg", (s_, chg), min_n=40))
            tbl(f"種牡馬別 {s_} 距離{chg}時 複勝率上位", top_table(st, "sire_dchg", (s_, chg), min_n=30))

    # ---- ペース・ラップ
    lines.extend(["## コース・距離別 ラップ傾向（レース数上位）", "",
                  "| コース | レース数 | 瞬発 | 持続 | 消耗 | 平均 |", "|---|--:|--:|--:|--:|--:|"])
    for cs, cnt in sorted(st.pace_freq.items(), key=lambda x: -sum(x[1].values()))[:40]:
        tot_ = sum(cnt.values())
        lines.append(f"| {cs[0]}{cs[1]}{cs[2]} | {tot_} | " + " | ".join(
            f"{cnt.get(k, 0) / tot_:.0%}" for k in ("瞬発", "持続", "消耗", "平均")) + " |")
    lines.append("")
    for pace in ("瞬発", "持続", "消耗", "平均"):
        rows = [(sty, st.get("style_pace", sty, pace)) for sty in ("逃げ", "先行", "差し", "追込")]
        tbl(f"{pace}戦の脚質別成績", [(a, c) for a, c in rows if c.n])
        tbl(f"種牡馬別 {pace}戦 複勝率上位", top_table(st, "sire_pace", (pace,), min_n=40))

    # ---- 脚質
    lines.extend(["## コース・距離別 脚質バイアス（複勝率, レース数上位）", "",
                  "| コース | 出走 | 逃げ | 先行 | 差し | 追込 |", "|---|--:|--:|--:|--:|--:|"])
    alls = sorted(((k[1:], c) for k, c in st.cells.items() if k[0] == "style_bias_all"), key=lambda x: -x[1].n)[:40]
    for cs, c in alls:
        vals = [st.get("style_bias", *cs, sty) for sty in ("逃げ", "先行", "差し", "追込")]
        lines.append(f"| {cs[0]}{cs[1]}{cs[2]} | {c.n} | " + " | ".join(
            f"{v.top3_rate:.0%}({v.n})" for v in vals) + " |")
    lines.append("")
    for s_ in ("芝", "ダ"):
        for gg in ("good", "soft"):
            rows = [(sty, st.get("style_going", s_, gg, sty)) for sty in ("逃げ", "先行", "差し", "追込")]
            tbl(f"{s_}・{'良' if gg == 'good' else '道悪'} の脚質別成績", [(a, c) for a, c in rows if c.n])
    lines.extend(["## 種牡馬別 産駒の脚質分布（出走200以上）", "", "| 種牡馬 | 出走 | 逃げ | 先行 | 差し | 追込 |",
                  "|---|--:|--:|--:|--:|--:|"])
    for sire, cnt in sorted(st.sire_style.items(), key=lambda x: -sum(x[1].values())):
        tot_ = sum(cnt.values())
        if tot_ < 200:
            break
        lines.append(f"| {sire} | {tot_} | " + " | ".join(f"{cnt.get(k, 0) / tot_:.0%}" for k in ("逃げ", "先行", "差し", "追込")) + " |")
    lines.append("")
    jst = [((k[1], k[2]), c) for k, c in st.cells.items() if k[0] == "jockey_style" and k[2] == "逃げ" and c.n >= 15]
    jst.sort(key=lambda x: -x[1].top3_rate)
    tbl("逃げた時の騎手成績 上位", [(f"{a}", c) for (a, _b), c in jst[:15]])
    for s_ in ("芝", "ダ"):
        for band, label in (("sprint", "短距離"), ("mile", "マイル"), ("middle", "中距離"), ("long", "長距離")):
            rows = []
            for k, c in st.cells.items():
                if k[0] == "agari_cs" and k[2] == s_ and k[3] == band and k[4] == "上がり上位" and c.n >= 30:
                    rows.append((k[1], c))
            rows.sort(key=lambda x: -x[1].top3_rate)
            tbl(f"上がり3F上位馬の複勝率（{s_}{label}・コース別 = 末脚の決まりやすさ）", rows)

    # ---- その他の要因
    def buckets(title, prefix, fixed, names):
        rows = [(nm, st.get(prefix, *fixed, nm)) if fixed else (nm, st.get(prefix, nm)) for nm in names]
        tbl(title, [(a, c) for a, c in rows if c.n])

    for s_ in ("芝", "ダ"):
        buckets(f"ローテーション別（{s_}）", "interval", (s_,),
                ["連闘", "中1週", "中2-4週", "中5-8週", "休み明け", "長期休養明け"])
        buckets(f"昇級・降級（{s_}）", "class_chg", (s_,), ["昇級", "同クラス", "降級"])
        buckets(f"斤量の前走比（{s_}）", "carried_chg", (s_,), ["斤量増", "同斤量", "斤量減"])
        tbl(f"叩き2戦目（{s_}）", [("叩き2戦目", st.get("second_after_rest", s_))])
        rows = [(f"{sx}・{se}", st.get("sex_season", sx, se, s_)) for sx in ("牡", "牝", "セ") for se in ("春", "夏", "秋", "冬")]
        tbl(f"性別×季節（{s_}）", [(a, c) for a, c in rows if c.n])
        rows = [(f"{ag}歳・{se}", st.get("age_season", ag, se, s_)) for ag in ("2", "3", "4", "5", "6+") for se in ("春", "夏", "秋", "冬")]
        tbl(f"年齢×季節（{s_}）", [(a, c) for a, c in rows if c.n])
        tbl(f"インブリード有無（{s_}）", [(("あり" if b else "なし"), st.get("has_cross", s_, b)) for b in (True, False)
                                     if st.get("has_cross", s_, b).n])
        cr = [(k[1], c) for k, c in st.cells.items() if k[0] == "cross" and k[2] == s_ and c.n >= 50]
        cr.sort(key=lambda x: -x[1].top3_rate)
        tbl(f"クロス祖先別（4×5以内, {s_}）複勝率上位", cr[:15])
        tbl(f"新馬・初出走の種牡馬（{s_}）勝率上位", top_table(st, "sire_debut", (s_,), min_n=15, sort="win"))
    buckets("騎手の継続/乗り替わり", "jockey_chg", (), ["継続", "乗替"])
    buckets("馬体重の前走比", "body_chg", (), ["大幅減", "減", "増減なし", "増", "大幅増"])
    tbl("調教師 休み明け 複勝率上位", top_table(st, "trainer_rest", ("休み明け",), min_n=20))
    tbl("調教師 デビュー戦 複勝率上位", top_table(st, "trainer_debut", (), min_n=15))
    rows = [(f"{k[1]}番人気", c) for k, c in sorted(((k, c) for k, c in st.cells.items() if k[0] == "popularity"),
                                                  key=lambda x: x[0][1]) if k[1] <= 18]
    tbl("人気別成績（単回収で妙味の目安）", rows)
    tbl("種牡馬 単勝回収率上位（芝, 出走100以上）", top_table(st, "sire_s", ("芝",), min_n=100, sort="roi"))
    tbl("種牡馬 単勝回収率上位（ダ, 出走100以上）", top_table(st, "sire_s", ("ダ",), min_n=100, sort="roi"))
    tbl("騎手 単勝回収率上位（騎乗200以上）", top_table(st, "jockey", (), min_n=200, sort="roi"))

    tbl("騎手 複勝率上位", top_table(st, "jockey", (), min_n=100))
    jt = [((k[1], k[2]), c) for k, c in st.cells.items() if k[0] == "jt" and c.n >= 20]
    jt.sort(key=lambda x: x[1].top3_rate, reverse=True)
    tbl("騎手×調教師 コンビ 複勝率上位", [(f"{a} × {b}", c) for (a, b), c in jt[:20]])
    return "\n".join(lines)


def dump_json(st: Stats, path) -> None:
    """集計セルを JSON で保存（他ツールや Claude が直接読めるように）."""
    out = [{"key": list(k), "n": c.n, "w": c.w, "t": c.t, "roi": round(c.roi, 3)}
           for k, c in st.cells.items() if c.n >= 5]
    with open(path, "w", encoding="utf-8") as f:
        json.dump({"base_top3": st.base_top3, "base_win": st.base_win, "n_races": st.n_races,
                   "pace_freq": [{"course": list(k), "freq": dict(v)} for k, v in st.pace_freq.items()],
                   "sire_style": {k: dict(v) for k, v in st.sire_style.items()},
                   "cells": out}, f, ensure_ascii=False)
