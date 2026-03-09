#!/usr/bin/env bash
set -euo pipefail

# HLTV CS2 Deep Analysis - Multi-Platform Installer
# Supports: Codex, Claude Code, Cline, OpenClaw

SKILL_NAME="hltv-cs2-deep-analysis"
REPO_URL="https://github.com/ulinwang/hltv-cs2-deep-analysis.git"

# Platform installation paths
declare -A PLATFORM_PATHS=(
    ["codex"]="$HOME/.codex/skills"
    ["claude"]="$HOME/.claude/skills"
    ["cline"]="$HOME/.cline/skills"
    ["openclaw"]="$HOME/.openclaw/skills"
)

# Detect platform if not specified
 detect_platform() {
    if [ -n "${PLATFORM:-}" ]; then
        echo "$PLATFORM"
        return
    fi

    # Auto-detect by checking which directory exists
    for platform in codex claude cline openclaw; do
        if [ -d "${PLATFORM_PATHS[$platform]}" ]; then
            echo "$platform"
            return
        fi
    done

    # Default to codex
    echo "codex"
}

PLATFORM=$(detect_platform)
INSTALL_DIR="${PLATFORM_PATHS[$PLATFORM]}/$SKILL_NAME"

echo "Platform: $PLATFORM"
echo "Install directory: $INSTALL_DIR"

# Create parent directory if needed
mkdir -p "$(dirname "$INSTALL_DIR")"

# Clone or update
if [ -d "$INSTALL_DIR/.git" ]; then
    echo "Updating existing installation..."
    cd "$INSTALL_DIR"
    git pull --ff-only
else
    echo "Cloning repository..."
    rm -rf "$INSTALL_DIR"  # Remove if exists but not a git repo
    git clone "$REPO_URL" "$INSTALL_DIR"
    cd "$INSTALL_DIR"
fi

# Install dependencies
echo "Installing dependencies..."
./scripts/install_deps.sh

echo ""
echo "✓ Installation complete!"
echo "  Platform: $PLATFORM"
echo "  Location: $INSTALL_DIR"
echo ""
echo "Usage:"
echo "  ./scripts/run_deep_analysis_pipeline.sh team 11283 falcons 'Falcons' output/falcons 2025-01-01 2025-12-31 50"
