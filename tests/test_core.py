import datetime as dt
import random

from keiba import analysis, db, knowledge as K
from keiba.betting import build_plan
from keiba.model import evaluate_race
from keiba.report import analyze_cards, select_races, write_week_report
from keiba.scraper import netkeiba as nk


def _blood_table_html(ped: dict) -> str:
    """位置→馬名 の辞書から netkeiba 形式(rowspan)の5代血統表を作る."""
    rows = [[] for _ in range(32)]
    span = {1: 16, 2: 8, 3: 4, 4: 2, 5: 1}

    def walk(pos, row):
        g = len(pos)
        rs = f' rowspan="{span[g]}"' if span[g] > 1 else ""
        rows[row].append(f'<td{rs}><a href="/horse/x/">{ped.get(pos, pos)}</a><br>2000 USA</td>')
        if g < 5:
            walk(pos + "S", row)
            walk(pos + "D", row + span[g] // 2)

    walk("S", 0)
    walk("D", 16)
    return '<table class="blood_table">' + "".join(f"<tr>{''.join(r)}</tr>" for r in rows) + "</table>"


def test_parse_pedigree_positions():
    ped = {"S": "キズナ", "SS": "ディープインパクト", "D": "母", "DS": "シンボリクリスエス",
           "SD": "キャットクイル", "SDS": "Storm Cat", "DD": "祖母", "DSS": "Kris S."}
    got = nk.parse_pedigree(_blood_table_html(ped))
    assert len(got) == 62
    for k, v in ped.items():
        assert got[k] == v
    assert got["SSSSS"] == "SSSSS" and got["DDDDD"] == "DDDDD"


def test_resolve_line_and_nick():
    assert K.resolve_line("キズナ") == "ディープインパクト系"
    assert K.resolve_line("未知の種牡馬", {"SS": "ディープインパクト"}, "S") == "ディープインパクト系"
    assert K.resolve_line(None, {"DSS": "Kris S."}, "DS") == "クリスエス系"
    r, notes = K.nick_prior("キズナ", "ディープインパクト系", "シンボリクリスエス", "シンボリクリスエス系")
    assert r == 1.5 and "ソングライン" in notes[0]
    r, _ = K.nick_prior("オルフェーヴル", "ステイゴールド系", "メジロマックイーン", "その他")
    assert r == 2


def test_detect_crosses_skips_derived_ancestors():
    ped = {"S": "A", "SS": "サンデーサイレンス", "SSS": "Halo", "D": "B", "DS": "C",
           "DSS": "サンデーサイレンス", "DSSS": "Halo"}
    crosses = K.detect_crosses(ped)
    assert crosses == [("サンデーサイレンス", "2×3")]


def test_family_detection():
    fam, bonus = K.detect_family({"D": "X", "DD": "アドマイヤグルーヴ"}, "X")
    assert fam == "ダイナカール" and bonus == 2


def test_classify_pace():
    assert nk.classify_pace([12.5, 11.5, 12.3, 12.4, 12.2, 11.4, 11.0, 11.3]) == "瞬発"
    assert nk.classify_pace([12.0, 10.5, 11.0, 11.8, 12.2, 12.5]) == "消耗"


def test_parse_result_minimal():
    html = """
    <dl class="racedata fc"><dd><h1>テストS(G3)</h1><p><diary_snap_cut><span>芝左1800m / 天候 : 晴 / 芝 : 稍重 / 発走 : 15:45</span></diary_snap_cut></p></dd></dl>
    <p class="smalltxt">2026年10月4日 4回東京2日目 3歳以上オープン</p>
    <table class="race_table_01">
    <tr><th>着順</th><th>枠番</th><th>馬番</th><th>馬名</th><th>性齢</th><th>斤量</th><th>騎手</th><th>タイム</th><th>着差</th><th>通過</th><th>上り</th><th>単勝</th><th>人気</th><th>馬体重</th><th>調教師</th></tr>
    <tr><td>1</td><td>3</td><td>5</td><td><a href="/horse/2022100001/">ウマA</a></td><td>牡4</td><td>57</td><td><a>騎手A</a></td><td>1:45.3</td><td></td><td>2-2</td><td>33.5</td><td>3.4</td><td>1</td><td>480(+2)</td><td><a>[東]調教師A</a></td></tr>
    <tr><td>2</td><td>7</td><td>13</td><td><a href="/horse/2022100002/">ウマB</a></td><td>牝3</td><td>54</td><td><a>騎手B</a></td><td>1:45.4</td><td>1/2</td><td>8-7</td><td>33.1</td><td>12.0</td><td>5</td><td>450(-4)</td><td><a>[西]調教師B</a></td></tr>
    </table>
    <table><tr><th>ラップ</th><td>12.6 - 11.2 - 11.5 - 11.9 - 11.8 - 11.6 - 11.4 - 11.1 - 11.6</td></tr></table>
    <table class="pay_table_01"><tr><th>単勝</th><td>5</td><td>340</td></tr><tr><th>馬連</th><td>5 - 13</td><td>1,560</td></tr></table>
    """
    race, res = nk.parse_result(html, "202605040211")
    assert race["course"] == "東京" and race["distance"] == 1800 and race["going"] == "稍重"
    assert race["grade"] == "G3" and race["name"] == "テストS" and race["date"] == "2026-10-04"
    assert len(race["laps"]) == 9 and race["pace_type"]
    assert race["payouts"]["馬連"] == [["5-13", 1560]]
    assert res[0]["horse_id"] == "2022100001" and res[0]["time_sec"] == 105.3
    assert res[1]["sex"] == "牝" and res[1]["age"] == 3 and res[1]["body_weight_diff"] == -4
    assert res[0]["trainer"] == "調教師A"


def _synthetic_db(tmp_path):
    conn = db.connect(tmp_path / "t.db")
    rng = random.Random(0)
    sires = [("キズナ", "シンボリクリスエス"), ("ロードカナロア", "ディープインパクト"),
             ("ヘニーヒューズ", "キングカメハメハ"), ("ゴールドシップ", "メジロマックイーン")]
    for i in range(40):
        s, ds = sires[i % 4]
        db.upsert_horse(conn, {"horse_id": f"h{i}", "name": f"馬{i}", "sire": s, "damsire": ds, "dam": f"母{i%10}",
                               "sire_line": K.resolve_line(s), "damsire_line": K.resolve_line(ds)})
    d0 = dt.date(2026, 6, 6)
    for r in range(60):
        rid = f"2026050{r:05d}"
        db.upsert_race(conn, {"race_id": rid, "date": (d0 + dt.timedelta(days=r)).isoformat(), "course": "東京",
                              "race_no": 11, "surface": "芝", "distance": [1600, 1800, 2000][r % 3], "going": "良",
                              "n_runners": 10, "grade": "OP", "pace_type": ["瞬発", "持続", "消耗"][r % 3]})
        horses = rng.sample(range(40), 10)
        # キズナ産駒(i%4==0)を強くする
        horses.sort(key=lambda i: rng.random() - (0.5 if i % 4 == 0 else 0))
        for fin, i in enumerate(horses, 1):
            pos = (i % 10) + 1  # 馬ごとに固定の位置取り
            db.upsert_result(conn, {"race_id": rid, "horse_id": f"h{i}", "finish": fin, "number": fin, "gate": (fin + 1) // 2,
                                    "age": 4, "jockey": f"J{i%5}", "trainer": f"T{i%3}", "odds": 5.0,
                                    "passing": f"{pos}-{pos}", "last3f": 33.0 + fin * 0.1,
                                    "time_sec": 107.0 + fin * 0.2 + (r % 3) * 12, "weight_carried": 55 + i % 3,
                                    "sex": "牝" if i % 2 else "牡", "popularity": fin, "body_weight_diff": (i % 5) * 4 - 8})
    conn.commit()
    return conn


def test_stats_and_model_end_to_end(tmp_path):
    conn = _synthetic_db(tmp_path)
    st = analysis.build_stats(conn)
    assert st.n_races == 60
    assert st.get("sire", "キズナ", "芝", "middle").top3_rate > st.base_top3
    card = {"race_id": "202605049911", "date": "2026-10-04", "course": "東京", "race_no": 11, "name": "テスト",
            "grade": "G2", "surface": "芝", "distance": 1800, "going": "良",
            "entries": [{"number": n + 1, "gate": n // 2 + 1, "name": f"馬{i}", "horse_id": f"h{i}", "age": 4,
                         "jockey": f"J{i%5}", "trainer": f"T{i%3}"} for n, i in enumerate([0, 1, 2, 3, 4, 5, 6, 7])]}
    ev = evaluate_race(card, st, conn, n_sims=2000)
    assert abs(sum(h.p_win for h in ev) - 1) < 1e-6
    assert abs(sum(h.p_top3 for h in ev) - 3) < 0.05
    assert ev[0].sire == "キズナ"
    plan = build_plan(ev)
    assert 1 <= len(plan.tickets) <= 10 and 0 < plan.p_any_hit <= 1
    analyzed = analyze_cards([card], st, conn)
    p = write_week_report(select_races(analyzed), dt.date(2026, 10, 3), 1, st, out_dir=tmp_path / "pred")
    text = p.read_text()
    assert "血統的根拠" in text and ("本線の買い目" in text or "◎軸の買い目" in text) and "展開予想" in text and "脚質" in text


def test_model_without_db_uses_priors():
    card = {"date": "2026-10-04", "course": "中山", "surface": "ダ", "distance": 1200, "going": "重", "grade": "OP",
            "entries": [
                {"number": 1, "name": "ダート短距離血統", "sire": "ヘニーヒューズ", "damsire": "サウスヴィグラス", "age": 4},
                {"number": 2, "name": "芝長距離血統", "sire": "ゴールドシップ", "damsire": "メジロマックイーン", "age": 4},
                {"number": 3, "name": "普通", "sire": "ルーラーシップ", "damsire": "クロフネ", "age": 4},
                {"number": 4, "name": "普通2", "sire": "モーリス", "damsire": "キングカメハメハ", "age": 4},
                {"number": 5, "name": "普通3", "sire": "キズナ", "damsire": "Storm Cat", "age": 4},
            ]}
    ev = evaluate_race(card, n_sims=1000)
    assert ev[0].name == "ダート短距離血統"
    assert ev[-1].name == "芝長距離血統"


def test_style_from_passing():
    from keiba.racing import style_from_passing
    assert style_from_passing("1-1-1-1", 16)[0] == "逃げ"
    assert style_from_passing("3-3-2-2", 16)[0] == "先行"
    assert style_from_passing("9-9-8-6", 16)[0] == "差し"
    assert style_from_passing("15-15-14-10", 16)[0] == "追込"
    assert style_from_passing(None, 16) == (None, None)


def test_pace_forecast_and_distance_profile():
    from keiba.racing import build_profile, forecast_pace
    card = {"course": "中山", "surface": "芝", "distance": 2000}
    hist_front = [{"finish": 1, "n_runners": 16, "passing": "1-1-1-1", "surface": "芝", "distance": 2000, "pace_type": "瞬発"}]
    hist_back = [{"finish": 2, "n_runners": 16, "passing": "14-14-12-8", "surface": "芝", "distance": 1600, "pace_type": "消耗"}]
    profs = [({"number": 1, "name": "逃げ馬"}, build_profile(hist_front, card))] + \
            [({"number": n, "name": f"差し{n}"}, build_profile(hist_back, card)) for n in range(2, 12)]
    fc = forecast_pace(profs, card)
    assert fc.nige == [(1, "逃げ馬")] and fc.pace == "スロー" and fc.pace_type == "瞬発"
    # 3頭の逃げ馬 → ハイペース
    profs3 = [({"number": n, "name": f"逃{n}"}, build_profile(hist_front, card)) for n in range(1, 4)] + profs[1:6]
    assert forecast_pace(profs3, card).pace == "ハイ"
    p = profs[1][1]
    assert p.dist_change == "延長" and p.style == "追込"
    assert "未経験" in p.dist_note


def test_summary_has_pace_style_distance(tmp_path):
    conn = _synthetic_db(tmp_path)
    st = analysis.build_stats(conn)
    md = analysis.summary_markdown(st)
    for kw in ("脚質バイアス", "ラップ傾向", "距離変化別", "瞬発戦の脚質別成績"):
        assert kw in md
    assert st.get("style_bias_all", "東京", "芝", 1800).n > 0
    assert st.get("dchg", "芝", "middle", "延長").n > 0


def test_factor_buckets():
    from keiba import factors as F
    assert F.interval_bucket(7) == "連闘" and F.interval_bucket(28) == "中2-4週" and F.interval_bucket(400) == "長期休養明け"
    assert F.class_bucket("2勝", "3勝") == "昇級" and F.class_bucket("G3", "OP") == "降級"
    assert F.jockey_bucket("A", "B") == "乗替" and F.carried_bucket(55, 57) == "斤量増"
    assert F.body_bucket(-12) == "大幅減" and F.season_of("2026-10-04") == "秋"
    assert F.course_exp_bucket([{"course": "東京", "surface": "芝", "finish": 2}], "東京", "芝") == "好走あり"


def test_other_factors_in_model(tmp_path):
    conn = _synthetic_db(tmp_path)
    st = analysis.build_stats(conn)
    assert st.standards and st.get("interval", "芝", "連闘").n + st.get("interval", "芝", "中1週").n > 0
    card = {"race_id": "x", "date": "2026-10-04", "course": "東京", "race_no": 11, "name": "テスト",
            "grade": "G2", "surface": "芝", "distance": 1800, "going": "良",
            "entries": [{"number": n + 1, "gate": n // 2 + 1, "name": f"馬{i}", "horse_id": f"h{i}", "age": 4,
                         "jockey": f"J{(i + 1) % 5}", "trainer": f"T{i%3}", "weight": 58 if n == 0 else 55}
                        for n, i in enumerate(range(8))]}
    ev = evaluate_race(card, st, conn, n_sims=500)
    text = "\n".join(e for h in ev for e in h.evidence)
    for kw in ("ローテ", "タイム指数", "斤量", "乗り替わり", "コース実績"):
        assert kw in text, kw
    assert any("time_index" in h.components for h in ev)
    md = analysis.summary_markdown(st)
    for kw in ("ローテーション別", "昇級・降級", "人気別成績", "年齢×季節"):
        assert kw in md


def test_target_races_only():
    from keiba.config import is_target_race
    assert is_target_race(11, "G2", "芝", "毎日王冠")
    assert is_target_race(7, "1勝", "ダ", "3歳以上1勝クラス")
    assert not is_target_race(6, "1勝", "ダ")
    assert not is_target_race(9, "未勝利", "芝", "2歳未勝利")
    assert not is_target_race(8, "OP", "障", "東京ハイジャンプ")


def test_deep_analysis_and_validation(tmp_path, monkeypatch):
    import json as _json
    from keiba import deep, validate, knowledge as K
    conn = _synthetic_db(tmp_path)
    for i in range(60):   # 払戻を入れる
        rid = f"2026050{i:05d}"
        conn.execute("UPDATE races SET payouts=? WHERE race_id=?", (_json.dumps({"単勝": [["1", 500]], "馬連": [["1-2", 1200]], "3連複": [["1-2-3", 3000]]}), rid))
    conn.commit()
    monkeypatch.setattr(deep, "OUT_DIR", tmp_path / "analysis")
    monkeypatch.setattr(deep, "LEARNED_PATH", tmp_path / "learned.json")
    monkeypatch.setattr(validate, "ROOT", tmp_path)
    monkeypatch.setattr(validate, "PARAMS_PATH", tmp_path / "params.json")
    res = deep.run(conn)
    assert res["races"] == 60 and res["sires"] >= 3
    learned = _json.loads((tmp_path / "learned.json").read_text())
    assert learned["sires"]["キズナ"]["apt"]["turf"] > learned["sires"]["ロードカナロア"]["apt"]["turf"]
    for fn in ("sires.md", "nicks_families.md", "courses.md", "market_value.md", "human_conditions.md", "README.md"):
        assert (tmp_path / "analysis" / fn).exists()
    text = validate.run(conn, "2026-07-06", "2026-08-04")
    assert "キャリブレーション" in text and "貢献度" in text and "推奨馬券" in text
    K.learned.cache_clear()


def test_merge_db(tmp_path):
    from keiba import db as D
    a = D.connect(tmp_path / "a.db")
    b = D.connect(tmp_path / "b.db")
    D.upsert_race(b, {"race_id": "202605040211", "date": "2026-10-04", "course": "東京", "race_no": 11, "surface": "芝"})
    D.upsert_horse(b, {"horse_id": "h1", "name": "馬"})
    b.commit()
    c = D.merge_into(a, tmp_path / "b.db")
    assert c["races"] == 1 and c["horses"] == 1
    assert D.merge_into(a, tmp_path / "b.db")["races"] == 0   # 重複は無視


def test_family_lineage_and_conditions():
    from keiba import family
    assert family.lineage("母A", "祖母B", {"祖母B": ["3代C", "4代D", "5代E"]}) == [
        ("母", "母A"), ("2代母", "祖母B"), ("3代母", "3代C"), ("4代母", "4代D")]
    assert family.lineage("母A", None, {}) == [("母", "母A")]
    ck = family.cond_keys("ダ", 1800, "重")
    assert ck["surface"] == ("ダ",) and ck["band"][0] == "ダ" and ck["going"][1] == "soft"
    assert family.cond_keys("障", 3000, "良") == {}


def test_trend_helpers():
    from keiba import trend
    assert trend.meet_stage("202605010112") == "開幕週"
    assert trend.meet_stage("202605010812") == "4週目以降"
    assert trend.going3("良(想定)") == "良" and trend.going3("稍重") == "稍重" and trend.going3("不良") == "重・不良"
    assert trend.norm_race_name("第70回 京王杯スプリングカップ(G2)") == "京王杯スプリングC"
