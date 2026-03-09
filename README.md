# HLTV CS2 Deep Analysis

[![Python 3.10+](https://img.shields.io/badge/python-3.10+-blue.svg)](https://www.python.org/downloads/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)

```bash
curl -fsSL https://raw.githubusercontent.com/ulinwang/hltv-cs2-deep-analysis/main/scripts/install_deps.sh | bash
```

基于 Playwright 的 HLTV CS2 深度数据分析工具，支持实时采集详细地图数据并生成中文可视化诊断报告。

## 功能特点

- **实时数据采集**：使用 Playwright 真实浏览器访问 HLTV，自动翻页抓取完整数据
- **高级指标分析**：采集 Rating、ADR、KAST、首杀、残局等 15+ 项深度指标
- **智能缺失值处理**：分层插补策略（地图中位数 → 对手中位数 → 全局中位数）
- **中文双格式报告**：同时生成 Markdown 文档和可视化 HTML 看板
- **可执行建议**：基于数据分析自动生成 P1/P2/P3 优先级改进建议
- **转会期支持**：可过滤特定队伍时期，分析选手在特定战队的表现

## 采集的高级指标

### 团队级指标
- `team_rating_3` - HLTV Team Rating 3.0
- `first_kills` - 首杀数对比
- `clutches_won` - 残局胜利数

### 个人聚合指标（队伍平均）
- `rating` - HLTV Rating 2.0
- `adr` - 平均每回合伤害
- `kast` - 参与回合率（%）
- `swing` - 回合影响力
- `opening_duel_diff` - 开局对枪差值
- `clutches_won` - 残局胜利数

### 最佳选手追踪
- `best_player` - 单图最佳选手
- `best_player_rating` - 最佳选手 Rating
- `best_player_adr` - 最佳选手 ADR

## 快速开始

### 1. 安装依赖

```bash
# 安装 Python 依赖和 Playwright
./scripts/install_deps.sh
```

依赖包括：Python 3.10+、Node.js/npm、pandas、jinja2、@playwright/cli

### 2. 一键分析（推荐）

```bash
./scripts/run_deep_analysis_pipeline.sh \
  team 11283 falcons "Falcons (kyousuke era)" \
  output/falcons_deep 2025-06-23 2026-02-20 30
```

参数说明：
- `team` - 分析类型（team 或 player）
- `11283` - HLTV 团队/选手 ID
- `falcons` - HLTV slug
- `"Falcons (kyousuke era)"` - 报告标题
- `output/falcons_deep` - 输出目录
- `2025-06-23` - 开始日期
- `2026-02-20` - 结束日期
- `30` - 最大采集地图数（0 表示无限制）

### 3. 高级参数配置

```bash
HLTV_COLLECTOR_EXTRA_ARGS="--headed --persistent --max-pages 8 --nav-timeout 180 --retries 3" \
HLTV_REPORT_EXTRA_ARGS="" \
./scripts/run_deep_analysis_pipeline.sh \
  team 11283 falcons "Falcons (kyousuke era)" \
  output/falcons_deep 2025-06-23 2026-02-20 30
```

### 4. 分步执行

**步骤 1：采集数据**

```bash
python3 scripts/collect_hltv_detailed.py \
  --subject-type team \
  --subject-id 11283 \
  --subject-slug falcons \
  --subject-label "Falcons (kyousuke era)" \
  --start-date 2025-06-23 \
  --end-date 2026-02-20 \
  --max-rows 30 \
  --max-pages 5 \
  --headed \
  --persistent \
  --output-csv output/falcons_deep/detailed_maps.csv
```

**步骤 2：生成报告**

```bash
python3 scripts/build_deep_report.py \
  --input-csv output/falcons_deep/detailed_maps.csv \
  --subject-label "Falcons (kyousuke era)" \
  --output-md output/falcons_deep/report.md \
  --output-html output/falcons_deep/report.html \
  --template-html assets/report_template.html
```

## 选手转会期分析

分析特定选手在特定战队时期的表现：

```bash
HLTV_COLLECTOR_EXTRA_ARGS="--headed --persistent --max-pages 12 --player-team-filter PARIVISION" \
HLTV_REPORT_EXTRA_ARGS="--player-team-filter PARIVISION" \
./scripts/run_deep_analysis_pipeline.sh \
  player 13776 jame "Jame (PARIVISION period)" \
  output/jame_parivision 2025-01-13 2026-03-02 0
```

## 报告内容

### Markdown 报告包含

- **执行摘要**：关键数据亮点
- **数据质量**：缺失值处理透明度
- **核心 KPI**：胜率、净回合差、加时率等
- **地图层诊断**：弱图/强图分析（含原因归因）
- **对手-地图组合诊断**：特定对手在特定地图的表现
- **可执行建议**：按 P1/P2/P3 优先级的改进方案
- **月度趋势**：时间维度表现追踪
- **对手总览**：高频对手的战绩统计

### HTML 看板包含

- 可视化图表和仪表盘
- 交互式数据表格
- 响应式设计，支持移动端查看

## 输出文件

```
output/
└── falcons_deep/
    ├── detailed_maps.csv    # 详细采集数据（含源链接）
    ├── report.md            # Markdown 分析报告
    └── report.html          # HTML 可视化看板
```

## 项目结构

```
.
├── scripts/
│   ├── collect_hltv_detailed.py      # 数据采集脚本（Playwright）
│   ├── build_deep_report.py          # 报告生成脚本
│   ├── run_deep_analysis_pipeline.sh # 一键执行流水线
│   ├── install_deps.sh               # 依赖安装脚本
│   └── build_quick_report.py         # 快速报告（无依赖模式）
├── assets/
│   └── report_template.html          # HTML 报告 Jinja2 模板
├── references/
│   └── schema-and-sources.md         # 数据规范与源说明
├── SKILL.md                          # Skill 使用文档
├── requirements.txt                  # Python 依赖
└── README.md                         # 本文件
```

## 采集脚本参数

```bash
python3 scripts/collect_hltv_detailed.py [选项]

必需参数:
  --subject-type {team,player}  分析主体类型
  --subject-id ID              HLTV 数字 ID
  --subject-slug SLUG          HLTV slug（如 falcons）
  --subject-label LABEL        报告显示名称
  --output-csv PATH           输出 CSV 路径

可选参数:
  --start-date YYYY-MM-DD     开始日期
  --end-date YYYY-MM-DD       结束日期
  --max-rows N               最大采集行数（0=无限制）
  --max-pages N              最大翻页数（0=无限制）
  --player-team-filter TOKEN  仅保留匹配的队伍（选手模式）
  --headed / --headless      有头/无头模式（默认：有头）
  --persistent / --ephemeral 持久/临时上下文（默认：持久）
  --browser BROWSER          浏览器类型（默认：chrome）
  --request-delay SECONDS    请求间隔（默认：0.2）
  --cli-timeout SECONDS      CLI 超时（默认：120）
  --nav-timeout SECONDS      导航超时（默认：120）
  --retries N               重试次数（默认：2）
  --retry-delay SECONDS     重试间隔（默认：1.0）
```

## 报告脚本参数

```bash
python3 scripts/build_deep_report.py [选项]

必需参数:
  --input-csv PATH           输入 CSV 路径
  --subject-label LABEL      报告标题
  --output-md PATH          Markdown 输出路径
  --output-html PATH        HTML 输出路径
  --template-html PATH      HTML 模板路径

可选参数:
  --player-team-filter TOKEN  仅分析特定队伍时期的数据
```

## 诊断规则

系统自动基于以下规则诊断强弱图：

| 问题类型 | 诊断条件 | 建议动作 |
|---------|---------|---------|
| 开局对枪劣势 | `opening_duel_diff < 0` | 增加双点争夺战术 |
| 首杀交换率低 | `first_kill_diff < 0` | 优化补枪与二次站位 |
| ADR 不足 | 低于均值 4+ | 增加道具先伤战术 |
| KAST 偏低 | 低于均值 3%+ | 优化双人绑定站位 |
| 残局劣势 | `clutch_diff < 0` | 建立残局脚本库 |
| 团队 Rating 劣势 | `team_rating_diff < 0` | 增加道具换位与夹击 |
| 个人 Rating 偏低 | 低于均值 0.05+ | 重分配经济与资源 |

## 数据质量说明

- **缺失值处理**：高级指标可能因 HLTV 数据缺失而为空，系统采用三层插补策略
- **透明度**：报告中会详细列出每列的缺失值处理情况
- **残余缺失**：若插补后仍有缺失，报告会明确标注

## 依赖项

- Python 3.10+
- pandas
- jinja2
- Node.js + npm
- @playwright/cli

## 许可证

MIT License

## 免责声明

本工具仅供数据分析学习使用。请遵守 HLTV 网站的服务条款，合理控制请求频率，避免对服务器造成压力。
