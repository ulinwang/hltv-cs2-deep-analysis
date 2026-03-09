#!/usr/bin/env python3
import argparse
import csv
from collections import defaultdict
from datetime import UTC, datetime
from pathlib import Path


def parse_args():
    p = argparse.ArgumentParser(description="Generate a quick fallback report from HLTV CSV (stdlib only).")
    p.add_argument("--input-csv", required=True)
    p.add_argument("--subject-label", required=True)
    p.add_argument("--output-md", required=True)
    p.add_argument("--output-html", required=True)
    p.add_argument("--player-team-filter", default=None)
    return p.parse_args()


def norm_key(text: str) -> str:
    return "".join(ch for ch in str(text or "").lower() if ch.isalnum())


def match_team_filter(row: dict, token: str) -> bool:
    key = norm_key(token)
    for col in ("player_team", "subject_team", "opponent_team", "mapstats_url", "source_url"):
        if key in norm_key(row.get(col, "")):
            return True
    return False


def to_int(v, default=0):
    try:
        return int(float(v))
    except Exception:  # noqa: BLE001
        return default


def pct(v: float) -> str:
    return f"{v * 100:.1f}%"


def signed(v: float) -> str:
    return f"+{v:.2f}" if v > 0 else f"{v:.2f}"


def load_rows(path: Path):
    with path.open(encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    for r in rows:
        if not r.get("round_diff"):
            r["round_diff"] = str(to_int(r.get("subject_rounds")) - to_int(r.get("opponent_rounds")))
        r["date"] = (r.get("date") or "").strip()
        r["result"] = (r.get("result") or "").strip().upper()
        r["round_diff"] = to_int(r.get("round_diff"))
    rows = [r for r in rows if r["date"]]
    rows.sort(key=lambda r: (r["date"], r.get("opponent", ""), r.get("map", "")))
    return rows


def group_stats(rows, group_key):
    g = defaultdict(list)
    for r in rows:
        g[group_key(r)].append(r)
    out = []
    for k, arr in g.items():
        maps = len(arr)
        wins = sum(1 for r in arr if r["result"] == "W")
        losses = maps - wins
        win_rate = wins / maps if maps else 0.0
        avg_round_diff = sum(r["round_diff"] for r in arr) / maps if maps else 0.0
        out.append(
            {
                "key": k,
                "maps": maps,
                "wins": wins,
                "losses": losses,
                "win_rate": win_rate,
                "avg_round_diff": avg_round_diff,
            }
        )
    return out


def write_markdown(ctx, output_path: Path):
    lines = [
        f"# {ctx['subject_label']} 速报（Fallback）",
        "",
        f"- 生成时间：{ctx['generated_at']}",
        f"- 样本区间：{ctx['date_min']} 到 {ctx['date_max']}",
        f"- 样本量：{ctx['total']} 张图",
        f"- 总战绩：{ctx['wins']}-{ctx['losses']}（胜率 {pct(ctx['win_rate'])}）",
        "- 说明：当前环境缺少 pandas/jinja2，已使用无第三方依赖的快速报告模板。",
        "",
        "## 地图表现",
        "| 地图 | 场次 | 胜 | 负 | 胜率 | 平均净回合差 |",
        "|---|---:|---:|---:|---:|---:|",
    ]
    for r in ctx["map_table"]:
        lines.append(
            f"| {r['key']} | {r['maps']} | {r['wins']} | {r['losses']} | {pct(r['win_rate'])} | {signed(r['avg_round_diff'])} |"
        )

    lines += [
        "",
        "## 对手表现（样本>=3）",
        "| 对手 | 场次 | 胜 | 负 | 胜率 | 平均净回合差 |",
        "|---|---:|---:|---:|---:|---:|",
    ]
    for r in ctx["opponent_table"]:
        lines.append(
            f"| {r['key']} | {r['maps']} | {r['wins']} | {r['losses']} | {pct(r['win_rate'])} | {signed(r['avg_round_diff'])} |"
        )

    lines += [
        "",
        "## 月度趋势",
        "| 月份 | 场次 | 胜 | 负 | 胜率 | 平均净回合差 |",
        "|---|---:|---:|---:|---:|---:|",
    ]
    for r in ctx["month_table"]:
        lines.append(
            f"| {r['key']} | {r['maps']} | {r['wins']} | {r['losses']} | {pct(r['win_rate'])} | {signed(r['avg_round_diff'])} |"
        )

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def write_html(ctx, output_path: Path):
    def table_rows(rows):
        return "".join(
            "<tr>"
            f"<td>{r['key']}</td>"
            f"<td>{r['maps']}</td>"
            f"<td>{r['wins']}</td>"
            f"<td>{r['losses']}</td>"
            f"<td>{pct(r['win_rate'])}</td>"
            f"<td>{signed(r['avg_round_diff'])}</td>"
            "</tr>"
            for r in rows
        )

    html = f"""<!doctype html>
<html lang="zh-CN">
<meta charset="utf-8">
<title>{ctx['subject_label']} 速报（Fallback）</title>
<style>
  body {{ font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif; max-width: 980px; margin: 24px auto; padding: 0 16px; line-height: 1.5; }}
  table {{ border-collapse: collapse; width: 100%; margin: 12px 0 24px; }}
  th, td {{ border: 1px solid #ddd; padding: 8px; text-align: left; }}
  th {{ background: #f5f5f5; }}
</style>
<h1>{ctx['subject_label']} 速报（Fallback）</h1>
<ul>
  <li>生成时间：{ctx['generated_at']}</li>
  <li>样本区间：{ctx['date_min']} 到 {ctx['date_max']}</li>
  <li>样本量：{ctx['total']} 张图</li>
  <li>总战绩：{ctx['wins']}-{ctx['losses']}（胜率 {pct(ctx['win_rate'])}）</li>
  <li>说明：当前环境缺少 pandas/jinja2，已使用无第三方依赖的快速报告模板。</li>
</ul>
<h2>地图表现</h2>
<table><tr><th>地图</th><th>场次</th><th>胜</th><th>负</th><th>胜率</th><th>平均净回合差</th></tr>{table_rows(ctx['map_table'])}</table>
<h2>对手表现（样本&gt;=3）</h2>
<table><tr><th>对手</th><th>场次</th><th>胜</th><th>负</th><th>胜率</th><th>平均净回合差</th></tr>{table_rows(ctx['opponent_table'])}</table>
<h2>月度趋势</h2>
<table><tr><th>月份</th><th>场次</th><th>胜</th><th>负</th><th>胜率</th><th>平均净回合差</th></tr>{table_rows(ctx['month_table'])}</table>
</html>
"""
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(html, encoding="utf-8")


def main():
    args = parse_args()
    rows = load_rows(Path(args.input_csv))
    if args.player_team_filter:
        rows = [r for r in rows if match_team_filter(r, args.player_team_filter)]
    if not rows:
        raise SystemExit("No rows after filtering.")

    total = len(rows)
    wins = sum(1 for r in rows if r["result"] == "W")
    losses = total - wins
    win_rate = wins / total if total else 0.0

    map_table = group_stats(rows, lambda r: r.get("map", ""))
    map_table.sort(key=lambda r: (-r["maps"], -r["win_rate"], -r["avg_round_diff"], r["key"]))

    opponent_table = group_stats(rows, lambda r: r.get("opponent", ""))
    opponent_table = [r for r in opponent_table if r["maps"] >= 3]
    opponent_table.sort(key=lambda r: (-r["maps"], -r["win_rate"], -r["avg_round_diff"], r["key"]))

    month_table = group_stats(rows, lambda r: r["date"][:7])
    month_table.sort(key=lambda r: r["key"])

    ctx = {
        "subject_label": args.subject_label,
        "generated_at": datetime.now(UTC).strftime("%Y-%m-%d %H:%M:%S UTC"),
        "date_min": rows[0]["date"],
        "date_max": rows[-1]["date"],
        "total": total,
        "wins": wins,
        "losses": losses,
        "win_rate": win_rate,
        "map_table": map_table,
        "opponent_table": opponent_table,
        "month_table": month_table,
    }
    write_markdown(ctx, Path(args.output_md))
    write_html(ctx, Path(args.output_html))
    print(f"rows={total}")
    print(f"md={args.output_md}")
    print(f"html={args.output_html}")


if __name__ == "__main__":
    main()
