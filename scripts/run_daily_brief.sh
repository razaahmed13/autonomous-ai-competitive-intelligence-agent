#!/usr/bin/env bash
set -euo pipefail

PROJECT_DIR="/home/ahmedraza/projects/autonomous-ai-competitive-intelligence-agent"
LOG_DIR="$PROJECT_DIR/logs"
LOCK_FILE="/tmp/ci-agent-daily.lock"

mkdir -p "$LOG_DIR"
cd "$PROJECT_DIR"

{
  echo "================================================================"
  echo "Daily AI Competitive Intelligence Brief started at $(date --iso-8601=seconds)"
  echo "Project: $PROJECT_DIR"

  # flock prevents overlapping runs and duplicate Slack posts if a previous/manual run is still active.
  flock -n "$LOCK_FILE" uv run python run.py all --send-slack

  echo "Daily AI Competitive Intelligence Brief finished at $(date --iso-8601=seconds)"
} >> "$LOG_DIR/daily-brief.log" 2>&1
