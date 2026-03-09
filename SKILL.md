---
name: hltv-cs2-deep-analysis
description: Download and analyze detailed HLTV CS2 match-map data for any team or player, then generate both Markdown and native HTML reports in Chinese. Use when users ask for deep diagnosis (weak maps, strong maps, opponent-map matchup issues) and transparent missing-data handling.
---

# HLTV CS2 Deep Analysis

Use this skill for end-to-end analysis: collect detailed rows online, compute deep indicators, handle missing values transparently, and output Chinese dual-format reports.

## Workflow

0. Install dependencies (recommended once, includes report + Playwright runtime check).
```bash
skills/hltv-cs2-deep-analysis/scripts/install_deps.sh
```
若不安装，pipeline 会自动回退生成 quick report（stdlib 版），并给出安装提示。
注意：采集依赖 `node/npm/npx` 与 `@playwright/cli`（通过 `npx` 拉取）。

1. Collect detailed rows online (real browser, not static HTML).
```bash
python3 skills/hltv-cs2-deep-analysis/scripts/collect_hltv_detailed.py \
  --subject-type team \
  --subject-id 11283 \
  --subject-slug falcons \
  --subject-label "Falcons (kyousuke era)" \
  --start-date 2025-06-23 \
  --end-date 2026-02-20 \
  --max-rows 30 \
  --max-pages 5 \
  --output-csv output/hltv/falcons_deep/detailed_maps.csv
```
默认建议 `--headed --persistent`（有头 + 持久上下文），更适合 HLTV。
脚本会自动翻页抓取（直到无下一页或达到 `--max-pages`）。

2. Build deep reports (Markdown + HTML).
```bash
python3 skills/hltv-cs2-deep-analysis/scripts/build_deep_report.py \
  --input-csv output/hltv/falcons_deep/detailed_maps.csv \
  --subject-label "Falcons (kyousuke era)" \
  --output-md output/hltv/falcons_deep/report.md \
  --output-html output/hltv/falcons_deep/report.html \
  --template-html skills/hltv-cs2-deep-analysis/assets/report_template.html
```
如需仅分析 player 的某支队伍阶段（转会期场景），可追加：
```bash
--player-team-filter PARIVISION
```

3. Run one-command pipeline (online path).
```bash
skills/hltv-cs2-deep-analysis/scripts/run_deep_analysis_pipeline.sh \
  team 11283 falcons "Falcons (kyousuke era)" \
  output/hltv/falcons_deep 2025-06-23 2026-02-20 30
```

传递采集/报告额外参数（推荐）：
```bash
HLTV_COLLECTOR_EXTRA_ARGS="--headed --persistent --max-pages 8 --nav-timeout 180 --cli-timeout 180 --retries 3 --retry-delay 1.5" \
HLTV_REPORT_EXTRA_ARGS="" \
skills/hltv-cs2-deep-analysis/scripts/run_deep_analysis_pipeline.sh \
  team 11283 falcons "Falcons (kyousuke era)" \
  output/hltv/falcons_deep 2025-06-23 2026-02-20 30
```

player 转会期样例（仅保留 Jame 在 PARIVISION 的样本）：
```bash
HLTV_COLLECTOR_EXTRA_ARGS="--headed --persistent --max-pages 12 --player-team-filter PARIVISION" \
HLTV_REPORT_EXTRA_ARGS="--player-team-filter PARIVISION" \
skills/hltv-cs2-deep-analysis/scripts/run_deep_analysis_pipeline.sh \
  player 13776 jame "Jame (PARIVISION period)" \
  output/hltv/jame_parivision 2025-01-13 2026-03-02 0
```

4. Collectable advanced fields per map.
- Team-level: `team_rating_3_subject/opponent`, `first_kills_subject/opponent`, `clutches_won_subject/opponent`.
- Player-derived aggregates (subject side): `rating`, `adr`, `kast`, `swing`, `opening_duel_diff`, `clutches_won`.
- Player spotlight: `best_player`, `best_player_rating`, `best_player_adr`.
- Player row context: `player_team`（用于 player 多队时期过滤与归属校准）。

5. Missing-data handling (built into report script).
- Report script applies hierarchical imputation for advanced metrics:
`地图中位数 -> 对手中位数 -> 全局中位数`（仅用于分析）。
- Report outputs a dedicated quality section:
  - total missing before/after
  - per-column fill counts
- If missing remains after fill, report will still generate and expose residual missing.

6. Analysis focus.
- 哪些图打得不好/好：胜率、净回合差、rating、ADR、KAST、开局对枪、首杀差、残局差。
- 对手为什么打得好：通过 `team_rating_3`、首杀与残局等对抗指标解释。
- 打哪些队的什么图不好/好：对手-地图组合层面的样本诊断与原因归纳。
- 自动生成“可执行建议”列表：按 `P1/P2/P3` 优先级输出执行动作、量化目标、覆盖范围。

## Output Expectations

- `detailed_maps.csv`: online-collected map rows with advanced metrics and source links.
- `report.md`: 中文深度诊断报告（弱图/强图、对手-地图组合、原因归因）。
- `report.html`: 中文原生 HTML 报告（可视化看板 + 诊断表格 + 可执行建议）。

## Resources

- `scripts/collect_hltv_detailed.py`: data collection from HLTV team/player stats pages.
- `scripts/build_deep_report.py`: deep indicator computation and dual-format report generation.
- `scripts/run_deep_analysis_pipeline.sh`: one-command pipeline.
- `references/schema-and-sources.md`: schema and data-quality rules.
- `assets/report_template.html`: native HTML template.
