#!/usr/bin/env python3
import argparse
from datetime import UTC, datetime
from pathlib import Path

try:
    import pandas as pd
except ModuleNotFoundError as exc:  # pragma: no cover - import guard
    raise SystemExit(
        "缺少依赖：pandas。\n"
        "请先执行：python3 -m pip install --user pandas jinja2\n"
        "或执行：skills/hltv-cs2-deep-analysis/scripts/install_deps.sh"
    ) from exc

try:
    from jinja2 import Template
except ModuleNotFoundError as exc:  # pragma: no cover - import guard
    raise SystemExit(
        "缺少依赖：jinja2。\n"
        "请先执行：python3 -m pip install --user pandas jinja2\n"
        "或执行：skills/hltv-cs2-deep-analysis/scripts/install_deps.sh"
    ) from exc


ADVANCED_NUM_COLS = [
    "rating",
    "adr",
    "kast",
    "swing",
    "opening_duel_diff",
    "clutches_won",
    "team_rating_3_subject",
    "team_rating_3_opponent",
    "first_kills_subject",
    "first_kills_opponent",
    "clutches_won_subject",
    "clutches_won_opponent",
]


def parse_args():
    parser = argparse.ArgumentParser(
        description="基于 HLTV 详细数据生成中文深度分析报告（Markdown + HTML）。"
    )
    parser.add_argument("--input-csv", required=True)
    parser.add_argument("--subject-label", required=True)
    parser.add_argument("--output-md", required=True)
    parser.add_argument("--output-html", required=True)
    parser.add_argument("--template-html", required=True, help="Jinja2 HTML 模板路径。")
    parser.add_argument(
        "--player-team-filter",
        default=None,
        help="仅保留 player_team 匹配该关键字的样本（用于转会期/特定队伍分析）。",
    )
    return parser.parse_args()


def to_numeric(df: pd.DataFrame, cols):
    for col in cols:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce")


def pct(x):
    return round(float(x) * 100, 1)


def signed(v):
    n = float(v)
    return f"+{n:.2f}" if n > 0 else f"{n:.2f}"


def norm_key(text: str) -> str:
    return "".join(ch for ch in str(text or "").lower() if ch.isalnum())


def team_filter_mask(df: pd.DataFrame, token: str):
    key = norm_key(token)
    candidate_cols = [c for c in ["player_team", "subject_team", "opponent_team", "mapstats_url", "source_url"] if c in df.columns]
    if not candidate_cols:
        return pd.Series([False] * len(df), index=df.index)
    mask = pd.Series([False] * len(df), index=df.index)
    for col in candidate_cols:
        mask = mask | df[col].fillna("").map(lambda x: key in norm_key(x))
    return mask


def fmt_reason_list(items):
    if not items:
        return "样本不足或指标接近均值，暂无明确单点问题。"
    return "；".join(items)


def split_reasons(reason_text: str):
    if not reason_text:
        return []
    return [x.strip() for x in str(reason_text).split("；") if x.strip()]


def dedupe_keep_order(items):
    seen = set()
    out = []
    for i in items:
        if i not in seen:
            seen.add(i)
            out.append(i)
    return out


def build_action_plan(weak_maps: list, weak_opp_maps: list):
    rule_map = {
        "开局对枪处于劣势": {
            "problem": "开局控图与先手权不足",
            "action": "将前20秒默认战术改为双点争夺：每图固定2套首杀战术（快抢/反清），并复盘前6回合首杀路线。",
            "target": "opening_duel_diff >= 0 且 first_kill_diff >= +0.5",
        },
        "对手首杀更多，回合先手权不足": {
            "problem": "首杀交换率低",
            "action": "提高首杀后的二次站位与补枪速度，限制单点独走，首杀后10秒必须形成2v1局部人数优势。",
            "target": "first_kill_diff 提升至少 +1.0（分图）",
        },
        "伤害输出（ADR）不足": {
            "problem": "中前期伤害不足",
            "action": "增加道具先伤后接战术：每个弱图新增2套默认道具伤害开局，并要求前40秒团队伤害达标。",
            "target": "ADR 提升到队伍均值以上（至少 +4）",
        },
        "存活/参与回合效率（KAST）偏低": {
            "problem": "回合稳定性与交易效率不足",
            "action": "以双人绑定站位为核心重做中后期默认；明确“先保枪再反清”的回合阈值，减少无信息单挑。",
            "target": "KAST 提升至少 +3pct",
        },
        "残局处理劣势（clutch 转化偏低）": {
            "problem": "残局胜率偏低",
            "action": "建立残局脚本库（1v1/2v2/2v3），训练“时间-道具-站位”三步决策，优先控雷包时间而非盲目找人。",
            "target": "clutch_diff >= 0 且 clutches_won_subject 提升",
        },
        "对手团队 Rating 3.0 更高": {
            "problem": "整体枪法对抗劣势",
            "action": "降低纯拼枪回合占比，增加道具换位与夹击回合；针对对手明星位设置一轮一限制（烟/闪/火）。",
            "target": "team_rating_3_subject - team_rating_3_opponent >= 0",
        },
        "个人综合 rating 偏低": {
            "problem": "个人状态与资源分配失衡",
            "action": "重分配经济与枪械资源给高影响位；将首发战术切到高成功率二人组并固定前6回合执行顺序。",
            "target": "rating 提升至少 +0.05",
        },
    }

    issue_buckets = {}
    for row in weak_maps + weak_opp_maps:
        title = row.get("title") or row.get("map", "")
        reasons = split_reasons(row.get("why_bad", ""))
        for rs in reasons:
            if rs not in rule_map:
                continue
            bucket = issue_buckets.setdefault(
                rs,
                {
                    "count": 0,
                    "scope": [],
                    "problem": rule_map[rs]["problem"],
                    "action": rule_map[rs]["action"],
                    "target": rule_map[rs]["target"],
                },
            )
            bucket["count"] += 1
            bucket["scope"].append(title)

    ranked = sorted(issue_buckets.items(), key=lambda kv: kv[1]["count"], reverse=True)

    actions = []
    for idx, (_, item) in enumerate(ranked[:6], start=1):
        priority = "P1" if idx <= 2 else ("P2" if idx <= 4 else "P3")
        scope = "、".join(dedupe_keep_order(item["scope"])[:4])
        actions.append(
            {
                "priority": priority,
                "problem": item["problem"],
                "action": item["action"],
                "target": item["target"],
                "scope": scope,
            }
        )

    # Add matchup-specific prescriptions for the worst opponent-map combos.
    for row in weak_opp_maps[:3]:
        actions.append(
            {
                "priority": "P1",
                "problem": f"{row['title']} 对位劣势",
                "action": (
                    f"为 {row['title']} 单独准备 BO3 地图脚本：前6回合固定默认 + 2套反制方案，"
                    "赛前演练对手高频默认点位的反清节奏。"
                ),
                "target": "该对位后续4图目标：胜率 >= 50%，平均净回合差 >= 0",
                "scope": row["title"],
            }
        )

    # Keep concise and unique by problem key.
    uniq = []
    seen = set()
    for a in actions:
        k = a["problem"]
        if k in seen:
            continue
        seen.add(k)
        uniq.append(a)
    return uniq[:8]


def apply_missing_strategy(df: pd.DataFrame):
    quality = {
        "缺失值填补策略": "按地图中位数 -> 按对手中位数 -> 全局中位数（仅用于分析，不改原始取数逻辑）",
        "列明细": [],
        "总缺失填补前": 0,
        "总缺失填补后": 0,
    }

    for col in ADVANCED_NUM_COLS:
        if col not in df.columns:
            continue
        before = int(df[col].isna().sum())
        quality["总缺失填补前"] += before
        if before > 0 and df[col].notna().any():
            df[col] = df[col].fillna(df.groupby("map")[col].transform("median"))
            df[col] = df[col].fillna(df.groupby("opponent")[col].transform("median"))
            df[col] = df[col].fillna(df[col].median())
        after = int(df[col].isna().sum())
        quality["总缺失填补后"] += after
        if before > 0:
            quality["列明细"].append({"列": col, "填补前": before, "填补后": after, "已填补": before - after})
    return df, quality


def enrich_base_columns(df: pd.DataFrame):
    if "round_diff" not in df.columns:
        df["round_diff"] = df["subject_rounds"] - df["opponent_rounds"]
    if "went_ot" not in df.columns:
        df["went_ot"] = ((df["subject_rounds"] > 13) | (df["opponent_rounds"] > 13)).astype(int)
    if "team_rating_3_subject" in df.columns and "team_rating_3_opponent" in df.columns:
        df["team_rating_diff"] = df["team_rating_3_subject"] - df["team_rating_3_opponent"]
    else:
        df["team_rating_diff"] = pd.NA
    if "first_kills_subject" in df.columns and "first_kills_opponent" in df.columns:
        df["first_kill_diff"] = df["first_kills_subject"] - df["first_kills_opponent"]
    else:
        df["first_kill_diff"] = pd.NA
    if "clutches_won_subject" in df.columns and "clutches_won_opponent" in df.columns:
        df["clutch_diff"] = df["clutches_won_subject"] - df["clutches_won_opponent"]
    else:
        df["clutch_diff"] = pd.NA
    return df


def metric_dict(df: pd.DataFrame):
    out = {}
    for col in ["rating", "adr", "kast", "team_rating_diff", "first_kill_diff", "clutch_diff"]:
        if col in df.columns:
            s = pd.to_numeric(df[col], errors="coerce").dropna()
            out[col] = float(s.mean()) if len(s) else None
        else:
            out[col] = None
    return out


def build_reasons(row: dict, baseline: dict):
    bad = []
    good = []
    if row["win_rate"] < 0.5:
        bad.append("胜率低于 50%")
    if row["avg_round_diff"] < 0:
        bad.append("净回合差为负")
    if row["rating"] is not None and baseline["rating"] is not None and row["rating"] < baseline["rating"] - 0.05:
        bad.append("个人综合 rating 偏低")
    if row["adr"] is not None and baseline["adr"] is not None and row["adr"] < baseline["adr"] - 4:
        bad.append("伤害输出（ADR）不足")
    if row["kast"] is not None and baseline["kast"] is not None and row["kast"] < baseline["kast"] - 3:
        bad.append("存活/参与回合效率（KAST）偏低")
    if row["opening_duel_diff"] is not None and row["opening_duel_diff"] < 0:
        bad.append("开局对枪处于劣势")
    if row["team_rating_diff"] is not None and row["team_rating_diff"] < 0:
        bad.append("对手团队 Rating 3.0 更高")
    if row["first_kill_diff"] is not None and row["first_kill_diff"] < 0:
        bad.append("对手首杀更多，回合先手权不足")
    if row["clutch_diff"] is not None and row["clutch_diff"] < 0:
        bad.append("残局处理劣势（clutch 转化偏低）")

    if row["win_rate"] >= 0.65:
        good.append("胜率显著高")
    if row["avg_round_diff"] >= 2:
        good.append("净回合差优势明显")
    if row["rating"] is not None and baseline["rating"] is not None and row["rating"] >= baseline["rating"] + 0.05:
        good.append("个人综合 rating 高于均值")
    if row["adr"] is not None and baseline["adr"] is not None and row["adr"] >= baseline["adr"] + 4:
        good.append("伤害输出（ADR）占优")
    if row["kast"] is not None and baseline["kast"] is not None and row["kast"] >= baseline["kast"] + 3:
        good.append("KAST 更高，回合稳定性更好")
    if row["opening_duel_diff"] is not None and row["opening_duel_diff"] > 0:
        good.append("开局对枪占优")
    if row["team_rating_diff"] is not None and row["team_rating_diff"] > 0:
        good.append("团队 Rating 3.0 优于对手")
    if row["first_kill_diff"] is not None and row["first_kill_diff"] > 0:
        good.append("首杀控制更好")
    if row["clutch_diff"] is not None and row["clutch_diff"] > 0:
        good.append("残局转化能力更强")

    return bad, good


def build_map_table(df: pd.DataFrame):
    agg = {
        "maps": ("map", "size"),
        "wins": ("result", lambda s: int((s.str.upper() == "W").sum())),
        "avg_round_diff": ("round_diff", "mean"),
        "ot_rate": ("went_ot", "mean"),
        "rating": ("rating", "mean"),
        "adr": ("adr", "mean"),
        "kast": ("kast", "mean"),
        "opening_duel_diff": ("opening_duel_diff", "mean"),
        "team_rating_diff": ("team_rating_diff", "mean"),
        "first_kill_diff": ("first_kill_diff", "mean"),
        "clutch_diff": ("clutch_diff", "mean"),
    }
    table = df.groupby("map").agg(**agg).reset_index()
    table["losses"] = table["maps"] - table["wins"]
    table["win_rate"] = table["wins"] / table["maps"]
    table = table.sort_values(["maps", "avg_round_diff"], ascending=[False, False])
    return table


def build_opp_map_table(df: pd.DataFrame):
    agg = {
        "maps": ("map", "size"),
        "wins": ("result", lambda s: int((s.str.upper() == "W").sum())),
        "avg_round_diff": ("round_diff", "mean"),
        "rating": ("rating", "mean"),
        "adr": ("adr", "mean"),
        "kast": ("kast", "mean"),
        "opening_duel_diff": ("opening_duel_diff", "mean"),
        "team_rating_diff": ("team_rating_diff", "mean"),
        "first_kill_diff": ("first_kill_diff", "mean"),
        "clutch_diff": ("clutch_diff", "mean"),
    }
    t = df.groupby(["opponent", "map"]).agg(**agg).reset_index()
    t["losses"] = t["maps"] - t["wins"]
    t["win_rate"] = t["wins"] / t["maps"]
    return t


def build_diagnosis(table: pd.DataFrame, baseline: dict, min_maps: int, top_n: int, by_opponent: bool):
    rows = []
    for _, r in table.iterrows():
        if int(r["maps"]) < min_maps:
            continue
        row = {
            "map": r.get("map"),
            "opponent": r.get("opponent"),
            "maps": int(r["maps"]),
            "wins": int(r["wins"]),
            "losses": int(r["losses"]),
            "win_rate": float(r["win_rate"]),
            "avg_round_diff": float(r["avg_round_diff"]),
            "rating": None if pd.isna(r.get("rating")) else float(r.get("rating")),
            "adr": None if pd.isna(r.get("adr")) else float(r.get("adr")),
            "kast": None if pd.isna(r.get("kast")) else float(r.get("kast")),
            "opening_duel_diff": None
            if pd.isna(r.get("opening_duel_diff"))
            else float(r.get("opening_duel_diff")),
            "team_rating_diff": None if pd.isna(r.get("team_rating_diff")) else float(r.get("team_rating_diff")),
            "first_kill_diff": None if pd.isna(r.get("first_kill_diff")) else float(r.get("first_kill_diff")),
            "clutch_diff": None if pd.isna(r.get("clutch_diff")) else float(r.get("clutch_diff")),
        }
        bad, good = build_reasons(row, baseline)
        row["bad_reasons"] = bad
        row["good_reasons"] = good
        row["bad_score"] = len(bad) + (1 if row["win_rate"] < 0.5 else 0)
        row["good_score"] = len(good) + (1 if row["win_rate"] >= 0.65 else 0)
        rows.append(row)

    bad_sorted = sorted(rows, key=lambda x: (-x["bad_score"], x["win_rate"], x["avg_round_diff"], -x["maps"]))
    good_sorted = sorted(rows, key=lambda x: (-x["good_score"], -x["win_rate"], -x["avg_round_diff"], -x["maps"]))

    bad = [r for r in bad_sorted if r["bad_score"] > 0][:top_n]
    good = [r for r in good_sorted if r["good_score"] > 0][:top_n]

    def to_out(items):
        out = []
        for r in items:
            title = f"{r['opponent']} - {r['map']}" if by_opponent else r["map"]
            out.append(
                {
                    "title": title,
                    "opponent": r.get("opponent"),
                    "map": r["map"],
                    "maps": r["maps"],
                    "record": f"{r['wins']}-{r['losses']}",
                    "win_rate_pct": pct(r["win_rate"]),
                    "avg_round_diff": round(r["avg_round_diff"], 2),
                    "why_bad": fmt_reason_list(r["bad_reasons"]),
                    "why_good": fmt_reason_list(r["good_reasons"]),
                }
            )
        return out

    return to_out(bad), to_out(good)


def build_context(df: pd.DataFrame, subject_label: str, player_team_filter: str | None = None):
    if df.empty:
        raise ValueError("输入 CSV 为空。")

    df = df.copy()
    if player_team_filter:
        df = df[team_filter_mask(df, player_team_filter)]
        if df.empty:
            raise ValueError(f"按 player_team_filter={player_team_filter} 过滤后无样本。")

    df["result"] = df["result"].astype(str).str.upper()
    df["date"] = pd.to_datetime(df["date"], errors="coerce")
    df = df.dropna(subset=["date"]).sort_values("date")
    to_numeric(
        df,
        ["subject_rounds", "opponent_rounds", "round_diff", "went_ot"] + ADVANCED_NUM_COLS,
    )
    df = enrich_base_columns(df)
    df, quality = apply_missing_strategy(df)

    total = len(df)
    wins = int((df["result"] == "W").sum())
    losses = total - wins
    win_rate = wins / total
    avg_round_diff = float(df["round_diff"].mean())
    ot_rate = float(df["went_ot"].mean())
    close_rate = float((df["round_diff"].abs() <= 3).mean())
    blowout_rate = float((df["round_diff"].abs() >= 7).mean())

    baseline = metric_dict(df)
    map_table = build_map_table(df)
    opp_map_table = build_opp_map_table(df)

    weak_maps, strong_maps = build_diagnosis(
        map_table, baseline=baseline, min_maps=3, top_n=6, by_opponent=False
    )
    weak_opp_maps, strong_opp_maps = build_diagnosis(
        opp_map_table, baseline=baseline, min_maps=2, top_n=8, by_opponent=True
    )
    action_plan = build_action_plan(weak_maps, weak_opp_maps)

    monthly = (
        df.assign(month=df["date"].dt.to_period("M").astype(str))
        .groupby("month")
        .agg(
            maps=("month", "size"),
            wins=("result", lambda s: int((s == "W").sum())),
            avg_round_diff=("round_diff", "mean"),
        )
        .reset_index()
    )
    monthly["win_rate"] = monthly["wins"] / monthly["maps"]

    opponent_table = (
        df.groupby("opponent")
        .agg(
            maps=("opponent", "size"),
            wins=("result", lambda s: int((s == "W").sum())),
            avg_round_diff=("round_diff", "mean"),
        )
        .reset_index()
        .sort_values(["maps", "wins"], ascending=[False, False])
    )
    opponent_table["losses"] = opponent_table["maps"] - opponent_table["wins"]
    opponent_table["win_rate"] = opponent_table["wins"] / opponent_table["maps"]
    opponent_table = opponent_table.head(10)

    best_maps = (
        df.sort_values(["round_diff", "date"], ascending=[False, True])
        .head(5)[["date", "opponent", "map", "subject_rounds", "opponent_rounds", "round_diff"]]
        .to_dict(orient="records")
    )
    worst_maps = (
        df.sort_values(["round_diff", "date"], ascending=[True, True])
        .head(5)[["date", "opponent", "map", "subject_rounds", "opponent_rounds", "round_diff"]]
        .to_dict(orient="records")
    )
    for item in best_maps + worst_maps:
        item["date"] = pd.Timestamp(item["date"]).strftime("%Y-%m-%d")

    highlights = [
        f"总图数 {total}，战绩 {wins}-{losses}，总胜率 {pct(win_rate)}%。",
        f"近似强度信号：平均净回合差 {avg_round_diff:.2f}，加时率 {pct(ot_rate)}%。",
        f"胶着局比例（|净回合差|<=3）{pct(close_rate)}%，碾压局比例（|净回合差|>=7）{pct(blowout_rate)}%。",
    ]
    if weak_maps:
        highlights.append(
            f"当前最需优先修复的地图：{weak_maps[0]['map']}（{weak_maps[0]['record']}，{weak_maps[0]['win_rate_pct']}%）。"
        )
    if strong_maps:
        highlights.append(
            f"当前最稳定的地图：{strong_maps[0]['map']}（{strong_maps[0]['record']}，{strong_maps[0]['win_rate_pct']}%）。"
        )
    if weak_opp_maps:
        highlights.append(
            f"最差对手-地图组合：{weak_opp_maps[0]['title']}（{weak_opp_maps[0]['record']}）。"
        )
    if strong_opp_maps:
        highlights.append(
            f"优势对手-地图组合：{strong_opp_maps[0]['title']}（{strong_opp_maps[0]['record']}）。"
        )

    optional_avgs = {}
    for col in ADVANCED_NUM_COLS:
        if col in df.columns:
            s = pd.to_numeric(df[col], errors="coerce").dropna()
            if len(s):
                optional_avgs[col] = round(float(s.mean()), 3)

    advanced_deltas = {}
    wins_df = df[df["result"] == "W"]
    losses_df = df[df["result"] == "L"]
    if "rating" in df.columns and len(wins_df) and len(losses_df):
        wr = wins_df["rating"].dropna()
        lr = losses_df["rating"].dropna()
        if len(wr) and len(lr):
            advanced_deltas["胜负_rating_差值"] = round(float(wr.mean() - lr.mean()), 3)
    if "team_rating_diff" in df.columns:
        td = df["team_rating_diff"].dropna()
        if len(td):
            advanced_deltas["团队_rating3_均值差"] = round(float(td.mean()), 3)
    if "first_kill_diff" in df.columns:
        fd = df["first_kill_diff"].dropna()
        if len(fd):
            advanced_deltas["首杀差_均值"] = round(float(fd.mean()), 3)

    return {
        "subject_label": subject_label,
        "generated_at": datetime.now(UTC).strftime("%Y-%m-%d %H:%M:%S UTC"),
        "date_min": df["date"].min().strftime("%Y-%m-%d"),
        "date_max": df["date"].max().strftime("%Y-%m-%d"),
        "total": total,
        "wins": wins,
        "losses": losses,
        "win_rate_pct": pct(win_rate),
        "avg_round_diff": round(avg_round_diff, 2),
        "ot_rate_pct": pct(ot_rate),
        "close_rate_pct": pct(close_rate),
        "blowout_rate_pct": pct(blowout_rate),
        "highlights": highlights,
        "quality": quality,
        "map_table": map_table.to_dict(orient="records"),
        "monthly_table": monthly.to_dict(orient="records"),
        "opponent_table": opponent_table.to_dict(orient="records"),
        "weak_maps": weak_maps,
        "strong_maps": strong_maps,
        "weak_opp_maps": weak_opp_maps,
        "strong_opp_maps": strong_opp_maps,
        "action_plan": action_plan,
        "optional_avgs": optional_avgs,
        "advanced_deltas": advanced_deltas,
        "best_maps": best_maps,
        "worst_maps": worst_maps,
    }


def write_markdown(ctx, output_md: Path):
    lines = []
    lines.append(f"# {ctx['subject_label']} 深度分析报告")
    lines.append("")
    lines.append(f"- 生成时间：{ctx['generated_at']}")
    lines.append(f"- 数据区间：{ctx['date_min']} 到 {ctx['date_max']}")
    lines.append(f"- 样本量：{ctx['total']} 张图")
    lines.append("")
    lines.append("## 执行摘要")
    for item in ctx["highlights"]:
        lines.append(f"- {item}")

    lines.append("")
    lines.append("## 数据质量与缺失处理")
    lines.append(f"- 缺失值填补策略：{ctx['quality']['缺失值填补策略']}")
    lines.append(f"- 缺失值总量（填补前）：{ctx['quality']['总缺失填补前']}")
    lines.append(f"- 缺失值总量（填补后）：{ctx['quality']['总缺失填补后']}")
    if ctx["quality"]["列明细"]:
        lines.append("- 列级处理明细：")
        lines.append("| 指标列 | 填补前 | 填补后 | 已填补 |")
        lines.append("|---|---:|---:|---:|")
        for row in ctx["quality"]["列明细"]:
            lines.append(f"| {row['列']} | {row['填补前']} | {row['填补后']} | {row['已填补']} |")

    lines.append("")
    lines.append("## 核心 KPI")
    lines.append(f"- 战绩：{ctx['wins']}-{ctx['losses']}（胜率 {ctx['win_rate_pct']}%）")
    lines.append(f"- 平均净回合差：{ctx['avg_round_diff']}")
    lines.append(f"- 加时率：{ctx['ot_rate_pct']}%")
    lines.append(f"- 胶着局占比：{ctx['close_rate_pct']}%")
    lines.append(f"- 碾压局占比：{ctx['blowout_rate_pct']}%")

    if ctx["optional_avgs"]:
        lines.append("")
        lines.append("## 高级指标均值")
        for k, v in ctx["optional_avgs"].items():
            lines.append(f"- {k}: {v}")

    if ctx["advanced_deltas"]:
        lines.append("")
        lines.append("## 高级差值指标")
        for k, v in ctx["advanced_deltas"].items():
            lines.append(f"- {k}: {v}")

    lines.append("")
    lines.append("## 地图层诊断：哪些图打得不好，为什么")
    if ctx["weak_maps"]:
        lines.append("| 地图 | 场次 | 战绩 | 胜率 | 平均净回合差 | 主要问题 |")
        lines.append("|---|---:|---:|---:|---:|---|")
        for row in ctx["weak_maps"]:
            lines.append(
                f"| {row['map']} | {row['maps']} | {row['record']} | {row['win_rate_pct']}% | {row['avg_round_diff']} | {row['why_bad']} |"
            )
    else:
        lines.append("- 暂无显著弱图。")

    lines.append("")
    lines.append("## 地图层诊断：哪些图打得好，为什么")
    if ctx["strong_maps"]:
        lines.append("| 地图 | 场次 | 战绩 | 胜率 | 平均净回合差 | 优势原因 |")
        lines.append("|---|---:|---:|---:|---:|---|")
        for row in ctx["strong_maps"]:
            lines.append(
                f"| {row['map']} | {row['maps']} | {row['record']} | {row['win_rate_pct']}% | {row['avg_round_diff']} | {row['why_good']} |"
            )
    else:
        lines.append("- 暂无显著强图。")

    lines.append("")
    lines.append("## 对手-地图组合诊断：打哪些队的什么图打得不好，为什么")
    if ctx["weak_opp_maps"]:
        lines.append("| 对手-地图 | 场次 | 战绩 | 胜率 | 平均净回合差 | 主要问题 |")
        lines.append("|---|---:|---:|---:|---:|---|")
        for row in ctx["weak_opp_maps"]:
            lines.append(
                f"| {row['title']} | {row['maps']} | {row['record']} | {row['win_rate_pct']}% | {row['avg_round_diff']} | {row['why_bad']} |"
            )
    else:
        lines.append("- 暂无显著劣势对手-地图组合。")

    lines.append("")
    lines.append("## 对手-地图组合诊断：打哪些队的什么图打得好，为什么")
    if ctx["strong_opp_maps"]:
        lines.append("| 对手-地图 | 场次 | 战绩 | 胜率 | 平均净回合差 | 优势原因 |")
        lines.append("|---|---:|---:|---:|---:|---|")
        for row in ctx["strong_opp_maps"]:
            lines.append(
                f"| {row['title']} | {row['maps']} | {row['record']} | {row['win_rate_pct']}% | {row['avg_round_diff']} | {row['why_good']} |"
            )
    else:
        lines.append("- 暂无显著优势对手-地图组合。")

    lines.append("")
    lines.append("## 可执行建议（按优先级）")
    if ctx["action_plan"]:
        lines.append("| 优先级 | 问题 | 执行动作 | 量化目标 | 覆盖范围 |")
        lines.append("|---|---|---|---|---|")
        for row in ctx["action_plan"]:
            lines.append(
                f"| {row['priority']} | {row['problem']} | {row['action']} | {row['target']} | {row['scope']} |"
            )
    else:
        lines.append("- 暂无需要输出的可执行建议。")

    lines.append("")
    lines.append("## 地图池总览")
    lines.append("| 地图 | 场次 | 胜 | 负 | 胜率 | 平均净回合差 | 加时率 |")
    lines.append("|---|---:|---:|---:|---:|---:|---:|")
    for row in ctx["map_table"]:
        lines.append(
            f"| {row['map']} | {int(row['maps'])} | {int(row['wins'])} | {int(row['losses'])} | "
            f"{pct(row['win_rate'])}% | {round(float(row['avg_round_diff']), 2)} | {pct(row['ot_rate'])}% |"
        )

    lines.append("")
    lines.append("## 月度趋势")
    lines.append("| 月份 | 场次 | 胜 | 胜率 | 平均净回合差 |")
    lines.append("|---|---:|---:|---:|---:|")
    for row in ctx["monthly_table"]:
        lines.append(
            f"| {row['month']} | {int(row['maps'])} | {int(row['wins'])} | {pct(row['win_rate'])}% | "
            f"{round(float(row['avg_round_diff']), 2)} |"
        )

    lines.append("")
    lines.append("## 对手总览（高样本）")
    lines.append("| 对手 | 场次 | 胜 | 负 | 胜率 | 平均净回合差 |")
    lines.append("|---|---:|---:|---:|---:|---:|")
    for row in ctx["opponent_table"]:
        lines.append(
            f"| {row['opponent']} | {int(row['maps'])} | {int(row['wins'])} | {int(row['losses'])} | "
            f"{pct(row['win_rate'])}% | {round(float(row['avg_round_diff']), 2)} |"
        )

    lines.append("")
    lines.append("## 单图极值（按净回合差）")
    lines.append("### 最佳 5 图")
    for row in ctx["best_maps"]:
        lines.append(
            f"- {row['date']} vs {row['opponent']}（{row['map']}）："
            f"{int(row['subject_rounds'])}-{int(row['opponent_rounds'])}（{signed(row['round_diff'])}）"
        )
    lines.append("### 最差 5 图")
    for row in ctx["worst_maps"]:
        lines.append(
            f"- {row['date']} vs {row['opponent']}（{row['map']}）："
            f"{int(row['subject_rounds'])}-{int(row['opponent_rounds'])}（{signed(row['round_diff'])}）"
        )

    output_md.parent.mkdir(parents=True, exist_ok=True)
    output_md.write_text("\n".join(lines))


def write_html(ctx, output_html: Path, template_path: Path):
    template = Template(template_path.read_text())
    html = template.render(ctx=ctx, pct=pct, round=round, float=float, int=int, signed=signed)
    output_html.parent.mkdir(parents=True, exist_ok=True)
    output_html.write_text(html)


def main():
    args = parse_args()
    df = pd.read_csv(args.input_csv)
    ctx = build_context(df, args.subject_label, player_team_filter=args.player_team_filter)
    write_markdown(ctx, Path(args.output_md))
    write_html(ctx, Path(args.output_html), Path(args.template_html))
    print(f"rows={ctx['total']}")
    print(f"md={args.output_md}")
    print(f"html={args.output_html}")


if __name__ == "__main__":
    main()
