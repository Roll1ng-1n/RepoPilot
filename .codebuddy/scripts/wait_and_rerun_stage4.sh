#!/usr/bin/env bash
# 等待中转站恢复后重跑被污染的 Stage 4 种子任务样本
# 用法: bash wait_and_rerun_stage4.sh
set -u
cd "/home/waaaaa/vibe coding/RepoPilot" || exit 1

INTERVAL=300        # 每次探测间隔（秒）
LOG=/tmp/repopilot-wait-rerun.log
: > "$LOG"

log() { echo "[$(date '+%F %T')] $*" | tee -a "$LOG"; }

log "开始等待中转站恢复（每 ${INTERVAL}s 探测一次）..."

while true; do
  PROBE_OUT=$(timeout 120 .venv/bin/repopilot probe --model gpt-5.6-luna 2>&1)
  if printf '%s' "$PROBE_OUT" | grep -q -- '- gpt-5.6-luna: passed'; then
    log "中转站已恢复，启动重跑 campaign..."
    nohup .venv/bin/repopilot campaign \
      --image repopilot-benchmark:py312-git \
      --model gpt-5.6-luna --model gpt-5.6-sol \
      --task seed-cross-file --task recovery-public-failure \
      --task replan-new-evidence --task workflow-long-chain \
      --task workflow-human-approval-git \
      --rounds 3 \
      > /tmp/repopilot-stage4-rerun.log 2>&1 &
    log "重跑 campaign PID=$!，日志 /tmp/repopilot-stage4-rerun.log"
    exit 0
  fi
  log "仍未恢复（$(printf '%s' "$PROBE_OUT" | grep -o 'APIConnectionError[^ ]*' | head -1)），继续等待..."
  sleep "$INTERVAL"
done
