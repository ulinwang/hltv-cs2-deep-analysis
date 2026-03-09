#!/usr/bin/env bash
set -euo pipefail

if [[ $# -lt 7 ]]; then
  echo "Usage:"
  echo "  $0 <subject_type> <subject_id> <subject_slug> <subject_label> <output_dir> <start_date> <end_date> [max_rows]"
  echo "Example:"
  echo "  $0 team 11283 falcons \"Falcons (kyousuke era)\" output/hltv/falcons 2025-06-23 2026-02-20 20"
  echo ""
  echo "Optional collector/report args via env:"
  echo "  HLTV_COLLECTOR_EXTRA_ARGS='--headed --persistent --max-pages 5 --player-team-filter PARIVISION'"
  echo "  HLTV_REPORT_EXTRA_ARGS='--player-team-filter PARIVISION'"
  exit 2
fi

SUBJECT_TYPE="$1"
SUBJECT_ID="$2"
SUBJECT_SLUG="$3"
SUBJECT_LABEL="$4"
OUTPUT_DIR="$5"
START_DATE="$6"
END_DATE="$7"
MAX_ROWS="${8:-0}"
COLLECTOR_EXTRA_ARGS="${HLTV_COLLECTOR_EXTRA_ARGS:-}"
REPORT_EXTRA_ARGS="${HLTV_REPORT_EXTRA_ARGS:-}"

COLLECTOR_FLAGS=()
if [[ -n "$COLLECTOR_EXTRA_ARGS" ]]; then
  # shellcheck disable=SC2206
  COLLECTOR_FLAGS=($COLLECTOR_EXTRA_ARGS)
fi

REPORT_FLAGS=()
if [[ -n "$REPORT_EXTRA_ARGS" ]]; then
  # shellcheck disable=SC2206
  REPORT_FLAGS=($REPORT_EXTRA_ARGS)
fi

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
TEMPLATE_HTML="$SCRIPT_DIR/../assets/report_template.html"

for cmd in node npm npx; do
  if ! command -v "$cmd" >/dev/null 2>&1; then
    echo "[error] missing required runtime: $cmd"
    echo "[hint] run: skills/hltv-cs2-deep-analysis/scripts/install_deps.sh"
    exit 1
  fi
done

if ! npx --yes --package @playwright/cli playwright-cli --help >/dev/null 2>&1; then
  echo "[error] playwright-cli is unavailable."
  echo "[hint] run: skills/hltv-cs2-deep-analysis/scripts/install_deps.sh"
  echo "[hint] if this persists, verify npm registry/network connectivity."
  exit 1
fi

mkdir -p "$OUTPUT_DIR"
DETAIL_CSV="$OUTPUT_DIR/detailed_maps.csv"
REPORT_MD="$OUTPUT_DIR/report.md"
REPORT_HTML="$OUTPUT_DIR/report.html"

python3 "$SCRIPT_DIR/collect_hltv_detailed.py" \
  --subject-type "$SUBJECT_TYPE" \
  --subject-id "$SUBJECT_ID" \
  --subject-slug "$SUBJECT_SLUG" \
  --subject-label "$SUBJECT_LABEL" \
  --start-date "$START_DATE" \
  --end-date "$END_DATE" \
  --max-rows "$MAX_ROWS" \
  --output-csv "$DETAIL_CSV" \
  "${COLLECTOR_FLAGS[@]}"

if python3 -c "import pandas, jinja2" >/dev/null 2>&1; then
  python3 "$SCRIPT_DIR/build_deep_report.py" \
    --input-csv "$DETAIL_CSV" \
    --subject-label "$SUBJECT_LABEL" \
    --output-md "$REPORT_MD" \
    --output-html "$REPORT_HTML" \
    --template-html "$TEMPLATE_HTML" \
    "${REPORT_FLAGS[@]}"
else
  echo "[warn] pandas/jinja2 not found; fallback to quick report (stdlib only)."
  echo "[hint] install full deps: skills/hltv-cs2-deep-analysis/scripts/install_deps.sh"
  python3 "$SCRIPT_DIR/build_quick_report.py" \
    --input-csv "$DETAIL_CSV" \
    --subject-label "$SUBJECT_LABEL" \
    --output-md "$REPORT_MD" \
    --output-html "$REPORT_HTML" \
    "${REPORT_FLAGS[@]}"
fi

echo "detailed_csv=$DETAIL_CSV"
echo "report_md=$REPORT_MD"
echo "report_html=$REPORT_HTML"
