"""多角的な切り口（2026-11-08 ユーザー「多角的に分析しろと言っただろ。分析あまいんだよ」）.
レース前に分かる条件を1頭ごとに列挙する。tools/multi_angle_scan.py（実績の総当たり）と keiba/digest.py（当日の材料）で同じ定義を使う."""
from __future__ import annotations

import datetime as dt

ROOT_D = (1200, 1600, 2000, 2400)


def race_conds(course, surface, distance, going, layout, n_runners, date) -> list[str]:
    co, su, d = course or "", surface or "", distance or 0
    out = [f"{co}{su}", f"{co}{su}{d}", f"{su}{d}"]
    if (going or "良")[0] in "稍重不":
        out.append(f"{su}・道悪")
    else:
        out.append(f"{su}・良")
    if d:  # 2026-11-08 ユーザー「該当コースでの騎手の成績を見ろ」: 競馬場×芝ダ×距離帯（例: 東京芝・2400以上）
        out.append(f"{co}{su}・" + ("〜1400" if d <= 1400 else "1500〜1800" if d <= 1800 else "1900〜2300" if d <= 2300 else "2400以上"))
    if co == "東京" or (co in ("新潟", "京都", "阪神") and "外" in (layout or "")):
        out.append(f"{su}・大箱")
    elif co in ("中山", "福島", "小倉", "札幌", "函館") or "内" in (layout or ""):
        out.append(f"{su}・小回り")
    if d:
        out.append(f"{su}・" + ("短距離" if d <= 1400 else "マイル" if d <= 1800 else "長距離" if d >= 2200 else "中距離"))
        out.append(f"{su}・" + ("根幹" if d in ROOT_D else "非根幹"))
    if n_runners:
        out.append("頭数" + ("〜12" if n_runners <= 12 else "13〜15" if n_runners <= 15 else "16〜"))
    if date:
        m = int(str(date)[5:7])
        out.append(f"{su}・" + ("春" if 3 <= m <= 5 else "夏" if 6 <= m <= 8 else "秋" if 9 <= m <= 11 else "冬"))
    return out


CLASS_RANK = {"新馬": 0, "未勝利": 0, "1勝": 1, "2勝": 2, "3勝": 3, "OP": 4, "L": 4, "G3": 5, "G2": 6, "G1": 7}


_JP = None


def jockey_prof(date, jockey, surface):
    """騎手×芝ダの [その年より前2年の3着内A/E, 先行率, 騎乗数]（tools/jockey_profile.py）."""
    global _JP
    if _JP is None:
        import json
        from pathlib import Path
        try:
            _JP = json.loads((Path(__file__).resolve().parents[1] / "data" / "knowledge" / "jockey_profile.json").read_text(encoding="utf-8"))
        except (OSError, ValueError):
            _JP = {}
    if not jockey or not date:
        return None
    return (_JP.get(str(date)[:4]) or {}).get(f"{jockey}|{surface}")


def horse_conds(surface, distance, gate, n_runners, age, sex, date, prev, weight=None, jockey=None, grade=None, bw_diff=None, course_region=None) -> list[str]:
    """prev: 前走 dict(date, distance, surface, finish, popularity, weight_carried, jockey, passing, n_runners, behind, grade) または None."""
    su, d = surface or "", distance or 0
    out = []
    if gate and n_runners:
        out.append(f"{su}・" + ("内枠" if gate <= 3 else "外枠" if gate >= 6 else "中枠"))
    if age:
        out.append(f"{su}・" + ("2歳" if age == 2 else "3歳" if age == 3 else "4歳" if age == 4 else "5歳以上"))
    if sex:
        out.append(f"{su}・" + ("牝" if str(sex).startswith("牝") else "牡セ"))
    if bw_diff is not None:
        try:
            b = int(bw_diff)
            out.append(f"{su}・馬体重" + ("+8kg以上" if b >= 8 else "-8kg以下" if b <= -8 else "±7kg以内"))
        except (TypeError, ValueError):
            pass
    # 騎手の腕前と乗り方の癖（2026-11-08 ユーザー「騎手のうまさでレース結果は変わる」）
    jp = jockey_prof(date, jockey, su)
    # 騎手の遠征（2026-11-08 三浦皇成の関西ダート A/E 0.82）: 本拠と逆の地域で乗るとき
    if jockey and date and _JP is not None:
        hm = (_JP.get(str(date)[:4]) or {}).get(f"@{jockey}")
        if hm and course_region:
            out.append(f"{su}・騎手が" + ("遠征（本拠と逆の地域）" if hm != course_region else "本拠の地域"))
    jstyle = None
    if jp:
        out.append(f"{su}・騎手の腕前" + ("上位" if jp[0] >= 1.10 else "下位" if jp[0] <= 0.90 else "中位"))
        jstyle = "先行させる騎手" if jp[1] >= 0.35 else "控える騎手" if jp[1] <= 0.15 else None
        if len(jp) > 3 and jp[3] >= 0.03:
            out.append(f"{su}・位置を下げる騎手")
        if jstyle:
            out.append(f"{su}・{jstyle}")
    if not prev:
        return out
    if jockey and prev.get("jockey") and jockey != prev["jockey"]:
        op = jockey_prof(date, prev["jockey"], su)
        if jp and op:
            dd = jp[0] - op[0]
            out.append(f"{su}・乗り替わり" + ("で騎手強化" if dd >= 0.10 else "で騎手弱化" if dd <= -0.10 else "（同程度）"))
    if jstyle:
        try:
            ppos = int(str(prev.get("passing")).split("-")[0]) / max(prev.get("n_runners") or 16, 1)
            pst = "前走逃げ先行" if ppos <= 0.25 else "前走後方" if ppos >= 0.6 else "前走中団"
            out.append(f"{su}・{pst}×{jstyle}")
        except (ValueError, TypeError):
            pass
    if prev.get("date") and date:
        try:
            wk = (dt.date.fromisoformat(str(date)[:10]) - dt.date.fromisoformat(str(prev["date"])[:10])).days // 7
            out.append(f"{su}・" + ("連闘〜中2週" if wk <= 3 else "中3〜8週" if wk <= 9 else "休み明け（中9週〜）"))
        except ValueError:
            pass
    pd_ = prev.get("distance") or 0
    if pd_ and d and prev.get("surface") == su:
        out.append(f"{su}・" + ("延長" if d > pd_ else "短縮" if d < pd_ else "同距離"))
        if abs(d - pd_) >= 400:
            out.append(f"{su}・" + ("大幅延長（400m〜）" if d > pd_ else "大幅短縮（400m〜）"))
    elif prev.get("surface") and prev.get("surface") != su:
        out.append(f"{su}・芝ダ替わり")
    f = prev.get("finish")
    if f:
        out.append(f"{su}・前走" + ("1〜3着" if f <= 3 else "4〜9着" if f <= 9 else "10着以下"))
        pp = prev.get("popularity")
        if pp:
            out.append(f"{su}・前走" + ("人気以上に好走" if f <= pp - 3 else "人気より凡走" if f >= pp + 4 else "人気なり"))
    if weight and prev.get("weight_carried"):
        w = float(weight) - float(prev["weight_carried"])
        out.append(f"{su}・斤量" + ("増" if w >= 1 else "減" if w <= -1 else "同"))
    if jockey and prev.get("jockey"):
        out.append(f"{su}・" + ("同騎手" if jockey == prev["jockey"] else "乗り替わり"))
    try:
        pos = int(str(prev.get("passing")).split("-")[0]) / max(prev.get("n_runners") or 16, 1)
        out.append(f"{su}・前走" + ("逃げ先行" if pos <= 0.25 else "後方" if pos >= 0.6 else "中団"))
    except (ValueError, TypeError):
        pass
    bh = prev.get("behind")
    if bh is not None and f and f > 1:
        out.append(f"{su}・前走" + ("0.5秒差以内" if bh <= 0.5 else "0.6〜1.0秒差" if bh <= 1.0 else "1.1秒差以上"))
    if grade and prev.get("grade") in CLASS_RANK and grade in CLASS_RANK:
        g0, g1 = CLASS_RANK[prev["grade"]], CLASS_RANK[grade]
        out.append(f"{su}・" + ("昇級" if g1 > g0 else "降級" if g1 < g0 else "同クラス"))
    return out


def region(course):
    return "東" if course in ("東京", "中山", "新潟", "福島", "札幌", "函館") else "西" if course else None
