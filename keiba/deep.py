"""取り込んだ実績データの徹底分析.

1. 種牡馬・母父の適性を実績から学習（12軸）→ data/knowledge/learned_sires.json（予想モデルが事前知識と合成して使う）
2. 多角的な分析レポート → docs/analysis/*.md
   - 種牡馬・母父の条件別プロファイル、統計的に有意な実測ニックス、牝系(兄弟)成績
   - 競馬場×距離のコース別カード（勝ち馬血統・脚質・枠・ペース・荒れ度・騎手・厩舎）
   - 人気・市場の歪み（回収率100%超の条件＝妙味、過剰人気の条件）
   - 騎手・調教師・ローテ・季節・馬場など

全て『出走数 n・3着内率・勝率・単勝回収率』と、全体平均との差の有意性(z値)で評価する。
"""
from __future__ import annotations

import json
import math
from collections import Counter, defaultdict
from pathlib import Path

from . import factors as F
from . import country, family, inbreed, trend
from .analysis import Cell
from .config import KNOWLEDGE_DIR, ROOT, distance_band, going_group
from .racing import style_from_passing

OUT_DIR = ROOT / "docs" / "analysis"
LEARNED_PATH = KNOWLEDGE_DIR / "learned_sires.json"

POWER_COURSES = {"中山", "阪神", "中京", "福島", "札幌", "函館"}   # 急坂・洋芝・小回り
KIRE_COURSES = {"東京", "京都", "新潟"}                          # 長い直線・平坦で瞬発力


# ---------------------------------------------------------------- 統計ユーティリティ

def z_score(t: int, n: int, p0: float) -> float:
    """3着内数 t / 出走 n が基準率 p0 からどれだけ離れているか（二項近似の z 値）."""
    if n == 0 or p0 <= 0 or p0 >= 1:
        return 0.0
    return (t - n * p0) / math.sqrt(n * p0 * (1 - p0))


def lift(c: Cell, base: float, k: float = 30.0) -> float:
    """縮約つきの log(3着内率 / 基準率)."""
    p = (c.t + k * base) / (c.n + k)
    return math.log(max(p, 1e-4) / max(base, 1e-4))


def fmt_cell(c: Cell) -> str:
    return f"{c.n} | {c.win_rate:.1%} | {c.top3_rate:.1%} | {c.roi * 100:.0f}%"


# ---------------------------------------------------------------- データ読み込み

def load_rows(conn) -> list[dict]:
    rows = conn.execute("""
        SELECT r.*, ra.date, ra.course, ra.surface, ra.distance, ra.going, ra.pace_type, ra.grade,
               ra.n_runners, ra.race_no, ra.name AS race_name,
               h.sire, h.damsire, h.dam, h.sire_line, h.damsire_line, h.family
        FROM results r JOIN races ra ON ra.race_id = r.race_id
        LEFT JOIN horses h ON h.horse_id = r.horse_id
        WHERE ra.surface IN ('芝','ダ')
        ORDER BY r.horse_id, ra.date
    """).fetchall()
    out = []
    prev = None
    for r in rows:
        d = dict(r)
        if prev is None or prev["horse_id"] != d["horse_id"]:
            prev = None
        d["band"] = distance_band(d["distance"] or 0)
        d["gg"] = going_group(d["going"])
        d["style"], d["esi"] = style_from_passing(d["passing"], d["n_runners"])
        d["season"] = F.season_of(d["date"])
        d["interval"] = F.interval_bucket(F.days_between(prev["date"], d["date"]) if prev else None)
        d["dchg"] = ("延長" if prev and d["distance"] - prev["distance"] >= 100 else
                     "短縮" if prev and d["distance"] - prev["distance"] <= -100 else "同" if prev else "初")
        d["ctype"] = "パワー型" if d["course"] in POWER_COURSES else "瞬発型"
        out.append(d)
        prev = d
    return out


def group(rows, keyf) -> dict:
    g: dict = defaultdict(Cell)
    for r in rows:
        k = keyf(r)
        if k is None or (isinstance(k, tuple) and None in k):
            continue
        g[k].add(r["finish"], r["odds"])
    return g


# ---------------------------------------------------------------- 1. 適性の学習

def learn_sire_aptitudes(rows: list[dict], who: str = "sire", min_n: int = 60) -> dict:
    """種牡馬(または母父)ごとに 12 軸の適性を実績から推定（-2〜+2）.

    各軸 = log(その父の条件内複勝率 / 全体の条件内複勝率) − log(その父の全体複勝率 / 全体複勝率)
    つまり『その条件で、父自身の平均的な強さ以上に走るか』。条件ごとの全体傾向（例: 若い馬ほど好走）を除く。
    芝/ダートは父自身の強さを含めた全体比（絶対的な強さ）。
    """
    tot = Cell()
    for r in rows:
        tot.add(r["finish"], r["odds"])
    base = tot.top3_rate or 0.2
    preds = {
        "sprint": lambda r: r["band"] == "sprint", "mile": lambda r: r["band"] == "mile",
        "middle": lambda r: r["band"] == "middle", "long": lambda r: r["band"] == "long",
        "heavy": lambda r: r["gg"] == "soft", "kire": lambda r: r["pace_type"] == "瞬発",
        "jizoku": lambda r: r["pace_type"] in ("持続", "消耗"), "power": lambda r: r["ctype"] == "パワー型",
        "early": lambda r: (r["age"] or 9) <= 2 or ((r["age"] or 9) == 3 and r["date"][5:7] <= "06"),
        "growth": lambda r: (r["age"] or 0) >= 5,
    }
    pop = {}
    for ax, f in preds.items():
        c = Cell()
        for r in rows:
            if f(r):
                c.add(r["finish"], r["odds"])
        pop[ax] = c.top3_rate or base
    surf_pop = {}
    for sname in ("芝", "ダ"):
        c = Cell()
        for r in rows:
            if r["surface"] == sname:
                c.add(r["finish"], r["odds"])
        surf_pop[sname] = c.top3_rate or base
    by = defaultdict(list)
    for r in rows:
        if r.get(who):
            by[r[who]].append(r)
    out = {}
    S = 4.0   # log-lift を -2〜+2 程度に写す係数

    def clip(x):
        return round(max(-2.0, min(2.0, x)), 2)
    for name, rs in by.items():
        if len(rs) < min_n:
            continue
        own = Cell()
        for r in rs:
            own.add(r["finish"], r["odds"])
        own_lift = lift(own, base)
        apt, ns = {}, {}
        for ax, sname in (("turf", "芝"), ("dirt", "ダ")):
            c = Cell()
            for r in rs:
                if r["surface"] == sname:
                    c.add(r["finish"], r["odds"])
            apt[ax], ns[ax] = clip(S * lift(c, surf_pop[sname])), c.n
        for ax, f in preds.items():
            c = Cell()
            for r in rs:
                if f(r):
                    c.add(r["finish"], r["odds"])
            apt[ax], ns[ax] = clip(S * (lift(c, pop[ax]) - own_lift)), c.n
        styles = Counter(r["style"] for r in rs if r["style"])
        out[name] = {"n": len(rs), "top3_rate": round(own.top3_rate, 4), "win_rate": round(own.win_rate, 4),
                     "roi": round(own.roi, 3), "apt": apt, "n_axis": ns,
                     "esi": round(sum(r["esi"] for r in rs if r["esi"] is not None) /
                                  max(1, sum(1 for r in rs if r["esi"] is not None)), 3),
                     "styles": dict(styles)}
    return out


def save_learned(rows) -> dict:
    learned = {
        "_meta": {"description": "実績データから学習した種牡馬・母父の適性（-2〜+2）。予想時に事前知識と出走数に応じて合成する。",
                  "n_rows": len(rows)},
        "sires": learn_sire_aptitudes(rows, "sire"),
        "damsires": learn_sire_aptitudes(rows, "damsire", min_n=80),
    }
    LEARNED_PATH.write_text(json.dumps(learned, ensure_ascii=False, indent=1), encoding="utf-8")
    return learned


# ---------------------------------------------------------------- 2. レポート

AX_JA = {"turf": "芝", "dirt": "ダ", "sprint": "短", "mile": "マ", "middle": "中", "long": "長", "heavy": "道悪",
         "kire": "瞬発", "jizoku": "持続", "power": "パワー", "early": "早熟", "growth": "成長"}


def _table(title: str, rows: list[tuple[str, Cell]], base: float, note: str = "") -> list[str]:
    L = [f"### {title}", ""]
    if note:
        L += [note, ""]
    if not rows:
        return L + ["（該当データ不足）", ""]
    L += ["| 条件 | 出走 | 勝率 | 複勝率 | 単回収 | z |", "|---|--:|--:|--:|--:|--:|"]
    for name, c in rows:
        L.append(f"| {name} | {fmt_cell(c)} | {z_score(c.t, c.n, base):+.1f} |")
    return L + [""]


def top_by(g: dict, base: float, min_n: int, n: int = 15, key="top3", reverse=True, label=lambda k: str(k)):
    items = [(k, c) for k, c in g.items() if c.n >= min_n]
    f = {"top3": lambda x: x[1].top3_rate, "roi": lambda x: x[1].roi,
         "z": lambda x: z_score(x[1].t, x[1].n, base), "win": lambda x: x[1].win_rate}[key]
    items.sort(key=f, reverse=reverse)
    return [(label(k), c) for k, c in items[:n]]


def report_sires(rows, learned, base) -> str:
    L = ["# 種牡馬・母父の徹底分析（自動生成）", "",
         f"対象: {len(rows)} 走（第7R以降・未勝利/障害除く）。全体の複勝率 {base:.1%}。z は全体平均との差の有意性（|z|≥2 で有意）。", ""]
    L += ["## 学習した種牡馬の適性（出走数上位）", "",
          "12軸の適性を実績から推定（+は得意、−は苦手）。芝/ダは同じ馬場の全体比、その他は『その条件の全体平均比』から父自身の平均的な強さを差し引いた値。", "",
          "| 種牡馬 | 出走 | 複勝率 | 単回収 | " + " | ".join(AX_JA.values()) + " | 主な脚質 |",
          "|---|--:|--:|--:|" + "--:|" * len(AX_JA) + "---|"]
    for name, d in sorted(learned["sires"].items(), key=lambda x: -x[1]["n"])[:60]:
        st = max(d["styles"], key=d["styles"].get) if d["styles"] else "-"
        L.append(f"| {name} | {d['n']} | {d['top3_rate']:.1%} | {d['roi']*100:.0f}% | " +
                 " | ".join(f"{d['apt'][a]:+.1f}" for a in AX_JA) + f" | {st} |")
    L.append("")
    for s in ("芝", "ダ"):
        for band, lab in (("sprint", "短距離"), ("mile", "マイル"), ("middle", "中距離"), ("long", "長距離")):
            sub = [r for r in rows if r["surface"] == s and r["band"] == band]
            if not sub:
                continue
            b = sum(1 for r in sub if (r["finish"] or 99) <= 3) / len(sub)
            g = group(sub, lambda r: r["sire"])
            L += _table(f"{s}{lab}: 種牡馬 複勝率上位（z順）", top_by(g, b, 30, key="z"), b)
    for gg, lab in (("soft", "道悪(稍重〜不良)"),):
        for s in ("芝", "ダ"):
            sub = [r for r in rows if r["surface"] == s and r["gg"] == gg]
            if sub:
                b = sum(1 for r in sub if (r["finish"] or 99) <= 3) / len(sub)
                L += _table(f"{s}{lab}: 種牡馬（z順）", top_by(group(sub, lambda r: r["sire"]), b, 20, key="z"), b)
    for pace in ("瞬発", "持続", "消耗"):
        sub = [r for r in rows if r["pace_type"] == pace]
        if sub:
            b = sum(1 for r in sub if (r["finish"] or 99) <= 3) / len(sub)
            L += _table(f"{pace}戦に強い種牡馬（z順）", top_by(group(sub, lambda r: r["sire"]), b, 20, key="z"), b)
    for s in ("芝", "ダ"):
        sub = [r for r in rows if r["surface"] == s]
        if sub:
            b = sum(1 for r in sub if (r["finish"] or 99) <= 3) / len(sub)
            L += _table(f"{s}: 母父 複勝率上位（z順）", top_by(group(sub, lambda r: r["damsire"]), b, 40, key="z"), b)
            L += _table(f"{s}: 母父系統", top_by(group(sub, lambda r: r["damsire_line"]), b, 60, key="z", n=20), b)
    return "\n".join(L)


def report_nicks(rows, base) -> str:
    L = ["# 実測ニックス・牝系の分析（自動生成）", ""]
    g = group(rows, lambda r: (r["sire"], r["damsire_line"]))
    sig = [(k, c) for k, c in g.items() if c.n >= 25]
    sig.sort(key=lambda x: -z_score(x[1].t, x[1].n, base))
    L += _table("好相性ニックス（父 × 母父系統, z上位）", [(f"{a} × {b}", c) for (a, b), c in sig[:30]], base,
                "父の平均ではなく全体平均比。父自身の強さを除いた相性は下の『父内相対』を参照。")
    # 父内相対（父の平均からの上振れ）
    sire_p = {k: c.top3_rate for k, c in group(rows, lambda r: r["sire"]).items()}
    rel = []
    for (s, dl), c in g.items():
        if c.n >= 25 and s in sire_p:
            rel.append(((s, dl), c, z_score(c.t, c.n, sire_p[s] or base)))
    rel.sort(key=lambda x: -x[2])
    L += ["### 父内相対でみたニックス（父の平均より上振れ, z上位）", "",
          "| 父 × 母父系統 | 出走 | 勝率 | 複勝率 | 単回収 | 父内z |", "|---|--:|--:|--:|--:|--:|"]
    for (s, dl), c, z in rel[:30]:
        L.append(f"| {s} × {dl} | {fmt_cell(c)} | {z:+.1f} |")
    L.append("")
    L += ["### 相性の悪い組み合わせ（父内z下位）", "", "| 父 × 母父系統 | 出走 | 勝率 | 複勝率 | 単回収 | 父内z |",
          "|---|--:|--:|--:|--:|--:|"]
    for (s, dl), c, z in rel[-15:]:
        L.append(f"| {s} × {dl} | {fmt_cell(c)} | {z:+.1f} |")
    L.append("")
    gl = group(rows, lambda r: (r["sire_line"], r["damsire_line"]))
    L += _table("系統×系統（z上位）", [(f"{a} × {b}", c) for (a, b), c in
                                    top_by(gl, base, 60, key="z", n=25, label=lambda k: k)], base)
    gd = group(rows, lambda r: r["dam"])
    L += _table("兄弟姉妹の成績が優秀な母（産駒の複勝率, 出走15以上）",
                top_by(gd, base, 15, key="z", n=30), base)
    gf = group(rows, lambda r: r["family"])
    L += _table("名門牝系（ナレッジ登録）の成績", top_by(gf, base, 10, key="z", n=20), base)
    return "\n".join(L)


def gate_label(r):
    g = r["gate"]
    if not g:
        return None
    return "内(1-3)" if g <= 3 else ("中(4-6)" if g <= 6 else "外(7-8)")


def report_courses(rows, base) -> str:
    L = ["# コース別カード（競馬場×芝ダ×距離, 自動生成）", "",
         "各コースの『勝ち馬の血統』『脚質』『枠』『ペース』『荒れ度』『騎手・厩舎』。", ""]
    by = defaultdict(list)
    for r in rows:
        by[(r["course"], r["surface"], r["distance"])].append(r)
    for key, rs in sorted(by.items(), key=lambda x: -len(x[1])):
        races = {r["race_id"] for r in rs}
        if len(races) < 8:
            continue
        b = sum(1 for r in rs if (r["finish"] or 99) <= 3) / len(rs)
        winners = [r for r in rs if r["finish"] == 1]
        L += [f"## {key[0]}{key[1]}{key[2]}m（{len(races)}レース）", ""]
        pop = [r["popularity"] for r in winners if r["popularity"]]
        fav = [r for r in rs if r["popularity"] == 1]
        favc = Cell()
        for r in fav:
            favc.add(r["finish"], r["odds"])
        paces = Counter(r["pace_type"] for r in winners if r["pace_type"])
        L.append(f"- 勝ち馬の平均人気: {sum(pop)/len(pop):.1f}番人気" if pop else "- 勝ち馬の人気: -")
        L.append(f"- 1番人気: 勝率{favc.win_rate:.0%} 複勝率{favc.top3_rate:.0%}（{favc.n}走）")
        if paces:
            L.append("- ラップ型: " + "、".join(f"{k}{v / sum(paces.values()):.0%}" for k, v in paces.most_common()))
        wl = [r["last3f"] for r in winners if r["last3f"]]
        if wl:
            L.append(f"- 勝ち馬の上がり3F平均: {sum(wl)/len(wl):.1f}秒")
        L.append("")
        L += ["| 区分 | 項目 | 出走 | 勝率 | 複勝率 | 単回収 | z |", "|---|---|--:|--:|--:|--:|--:|"]
        for lab, f in (("脚質", lambda r: r["style"]), ("枠", gate_label)):
            g = group(rs, f)
            for k in sorted(g):
                c = g[k]
                L.append(f"| {lab} | {k} | {fmt_cell(c)} | {z_score(c.t, c.n, b):+.1f} |")
        for lab, f, mn in (("父系統", lambda r: r["sire_line"], 15), ("種牡馬", lambda r: r["sire"], 10),
                           ("母父系統", lambda r: r["damsire_line"], 15), ("騎手", lambda r: r["jockey"], 10),
                           ("調教師", lambda r: r["trainer"], 8)):
            for k, c in top_by(group(rs, f), b, mn, key="z", n=5):
                L.append(f"| {lab} | {k} | {fmt_cell(c)} | {z_score(c.t, c.n, b):+.1f} |")
        L.append("")
    return "\n".join(L)


def report_market(rows, base) -> str:
    L = ["# 市場の歪み・妙味の分析（自動生成）", "",
         "単勝回収率100%超の条件は『人気以上に走る』＝妙味。出走数が少ないと偶然の可能性が高いので、出走数と z を併せて見る。", ""]
    g = group(rows, lambda r: r["popularity"])
    L += _table("人気別成績", [(f"{k}番人気", g[k]) for k in sorted(g) if k and k <= 18], base)
    segs = {
        "種牡馬×芝ダ×距離帯": lambda r: (r["sire"], r["surface"], r["band"]),
        "種牡馬×競馬場×芝ダ": lambda r: (r["sire"], r["course"], r["surface"]),
        "母父×芝ダ": lambda r: (r["damsire"], r["surface"]),
        "騎手×競馬場": lambda r: (r["jockey"], r["course"]),
        "調教師×芝ダ": lambda r: (r["trainer"], r["surface"]),
        "系統×距離変化": lambda r: (r["sire_line"], r["surface"], r["dchg"]),
        "系統×道悪": lambda r: (r["sire_line"], r["surface"], r["gg"]),
        "ローテ×クラス": lambda r: (r["interval"], r["grade"]),
    }
    for lab, f in segs.items():
        gg = group(rows, f)
        good = [(k, c) for k, c in gg.items() if c.n >= 40 and c.roi >= 1.0]
        good.sort(key=lambda x: -x[1].roi)
        L += _table(f"妙味あり: {lab}（単回収100%以上, 出走40以上）",
                    [(" × ".join(map(str, k)), c) for k, c in good[:20]], base)
        bad = [(k, c) for k, c in gg.items() if c.n >= 60 and c.roi <= 0.5]
        bad.sort(key=lambda x: x[1].roi)
        L += _table(f"過剰人気: {lab}（単回収50%以下, 出走60以上）",
                    [(" × ".join(map(str, k)), c) for k, c in bad[:10]], base)
    return "\n".join(L)


def report_human_and_conditions(rows, base) -> str:
    L = ["# 騎手・調教師・ローテ・季節・馬場の分析（自動生成）", ""]
    for lab, f, mn in (("騎手", lambda r: r["jockey"], 100), ("調教師", lambda r: r["trainer"], 60),
                       ("騎手×調教師", lambda r: (r["jockey"], r["trainer"]), 20)):
        L += _table(f"{lab}（z上位）", top_by(group(rows, f), base, mn, key="z", n=25,
                                            label=lambda k: " × ".join(k) if isinstance(k, tuple) else k), base)
    for lab, f in (("ローテーション", lambda r: r["interval"]), ("距離変化", lambda r: (r["surface"], r["dchg"])),
                   ("季節×性別", lambda r: (r["season"], r["sex"])), ("年齢", lambda r: r["age"]),
                   ("馬場×脚質", lambda r: (r["surface"], r["gg"], r["style"])),
                   ("クラス×脚質", lambda r: (r["grade"], r["style"])),
                   ("頭数×脚質", lambda r: (F.field_size_bucket(r["n_runners"]), r["style"]))):
        g = group(rows, f)
        L += _table(lab, [(" × ".join(map(str, k)) if isinstance(k, tuple) else str(k), g[k])
                          for k in sorted(g, key=str) if g[k].n >= 30], base)
    return "\n".join(L)


def report_course_form(rows, base) -> str:
    """コース形態（直線の長さ・坂・大回り/小回り・回り）×脚質・種牡馬・頭数."""
    from . import knowledge as K
    for r in rows:
        a = K.course_attrs(r["course"], r["surface"], r["distance"])
        r["straight_cat"], r["slope"], r["turn"], r["dir"] = a["straight_cat"], a["slope"], a["turn"], a["direction"]
        r["field"] = F.field_size_bucket(r["n_runners"])
    L = ["# コース形態・頭数の分析（自動生成）", "",
         "直線の長さ（長≥450m/中/短<350m）、坂（坂=東京・中山・阪神・中京）、コーナー（大回り/小回り）、回り、頭数ごとの傾向。", ""]
    for lab, f in (("直線×脚質", lambda r: (r["surface"], "直線" + r["straight_cat"], r["style"])),
                   ("坂×脚質", lambda r: (r["surface"], r["slope"], r["style"])),
                   ("コーナー×脚質", lambda r: (r["surface"], r["turn"], r["style"])),
                   ("頭数×脚質", lambda r: (r["surface"], r["field"], r["style"]))):
        g = group(rows, f)
        L += _table(lab, [(" × ".join(map(str, k)), g[k]) for k in sorted(g, key=str) if g[k].n >= 100], base)
    for attr, vals, lab in (("straight_cat", ("長", "短"), "直線"), ("slope", ("坂", "平坦"), "坂"),
                            ("turn", ("大回り", "小回り"), "コーナー"), ("dir", ("右", "左"), "回り"),
                            ("field", ("多頭数(15〜)", "少頭数(〜10)"), "頭数")):
        for s_ in ("芝", "ダ"):
            sub = [r for r in rows if r["surface"] == s_]
            sire_all = {k: c.top3_rate for k, c in group(sub, lambda r: r["sire"]).items()}
            for v in vals:
                g = group([r for r in sub if r[attr] == v], lambda r: r["sire"])
                rel = [(k, c, z_score(c.t, c.n, sire_all.get(k) or base)) for k, c in g.items() if c.n >= 40]
                rel.sort(key=lambda x: -x[2])
                L += [f"### {s_}・{lab}{v}で父自身の平均より走る種牡馬（父内z上位）", "",
                      "| 種牡馬 | 出走 | 勝率 | 複勝率 | 単回収 | 父内z |", "|---|--:|--:|--:|--:|--:|"]
                L += [f"| {k} | {fmt_cell(c)} | {z:+.1f} |" for k, c, z in rel[:12]] + [""]
    return "\n".join(L)


def run(conn) -> dict:
    rows = load_rows(conn)
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    if not rows:
        (OUT_DIR / "README.md").write_text("# 分析レポート\n\nまだ実績データがありません。\n", encoding="utf-8")
        return {"rows": 0}
    tot = Cell()
    for r in rows:
        tot.add(r["finish"], r["odds"])
    base = tot.top3_rate
    learned = save_learned(rows)
    files = {
        "sires.md": report_sires(rows, learned, base),
        "nicks_families.md": report_nicks(rows, base),
        "courses.md": report_courses(rows, base),
        "market_value.md": report_market(rows, base),
        "human_conditions.md": report_human_and_conditions(rows, base),
        "course_form.md": report_course_form(rows, base),
        "trends.md": trend.report(rows),
        "family.md": family.report(conn),
        "country_types.md": country.report(conn),
        "crosses.md": inbreed.report(conn),
    }
    for fn, text in files.items():
        (OUT_DIR / fn).write_text(text, encoding="utf-8")
    races = {r["race_id"] for r in rows}
    dates = sorted(r["date"] for r in rows)
    idx = ["# 分析レポート（取り込みデータから自動生成）", "",
           f"- 対象: {len(races)} レース / {len(rows)} 走（{dates[0]} 〜 {dates[-1]}、第7R以降・未勝利/障害除く）",
           f"- 全体: 勝率 {tot.win_rate:.1%} / 複勝率 {tot.top3_rate:.1%}",
           f"- 学習した種牡馬 {len(learned['sires'])} 頭・母父 {len(learned['damsires'])} 頭 → `data/knowledge/learned_sires.json`", "",
           "| レポート | 内容 |", "|---|---|",
           "| [sires.md](sires.md) | 種牡馬の学習適性（12軸）、条件別の強い種牡馬、道悪・ペース別、母父・母父系統 |",
           "| [nicks_families.md](nicks_families.md) | 実測ニックス（全体比・父内相対）、系統×系統、兄弟の成績が優秀な母、名門牝系 |",
           "| [courses.md](courses.md) | コース別カード（荒れ度・1番人気・ラップ型・脚質・枠・血統・騎手・厩舎） |",
           "| [market_value.md](market_value.md) | 人気別成績、回収率で見た妙味と過剰人気の条件 |",
           "| [human_conditions.md](human_conditions.md) | 騎手・調教師・コンビ、ローテ、距離変化、季節、馬場×脚質、頭数 |",
           "| [course_form.md](course_form.md) | 直線の長さ・坂・大回り/小回り・回り・頭数 × 脚質／種牡馬 |",
           "| [crosses.md](crosses.md) | 5代以内のクロス（祖先・濃さ別）の人気比と期間別の再現性（5代血統表の補完に応じて自動更新） |",
           "| [country_types.md](country_types.md) | 国別タイプ（日本型・米国型・欧州型）の年別・条件別の人気比と、開催の偏りが続くかの検証 |",
           "| [family.md](family.md) | 牝系（兄弟・2代母の一族）の条件適性の検証と、有力馬を出し続けている牝系 |",
           "| [trends.md](trends.md) | 傾向の波: 同名レースの連続好走血統・血統の勢い・今の開催の馬場傾向（翌年/翌週も続くかの検証つき） |",
           "| [value_segments.md](value_segments.md) | 条件×人気帯の回収率（発見→確認→未使用期間テストの3段階で検証した妙味条件） |",
           "| [expert_check.md](expert_check.md) | 専門家見解（亀谷・望田・水上・坂上 等）の実績による検証 |",
           "| [learned_weights.md](learned_weights.md) | 市場（人気）を土台に学習した各要素の重みと、期待値で選んだ場合の回収率 |",
           "| [backtest.md](backtest.md) | 予想モデルの検証（的中率・回収率・キャリブレーション・要素の貢献度） |", ""]
    (OUT_DIR / "README.md").write_text("\n".join(idx), encoding="utf-8")
    return {"rows": len(rows), "races": len(races), "sires": len(learned["sires"])}
