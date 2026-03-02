#!/usr/bin/env bash
set -euo pipefail
# Daily pipeline runner via cron
# Runs the full scrape → score → email → send pipeline
#
# Usage in crontab:
#   30 4 * * * cd /workspaces/jht && ./scripts/run_daily.sh >> logs/pipeline.log 2>&1

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"

cd "$PROJECT_DIR"

# Load env if present
if [ -f backend/.env ]; then
    set -a
    source backend/.env
    set +a
fi

# Activate venv if present
if [ -f .venv/bin/activate ]; then
    source .venv/bin/activate
fi

mkdir -p logs

echo "===== Pipeline run: $(date -u '+%Y-%m-%d %H:%M:%S UTC') ====="
python -m backend.app.pipeline
echo "===== Pipeline complete: $(date -u '+%Y-%m-%d %H:%M:%S UTC') ====="
