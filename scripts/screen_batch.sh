#!/usr/bin/env bash
# Nightly batch wrapper around `python -m screening screen`, for cron/Autosys.
#
#   screen_batch.sh <customer_file.csv>
#
# Exit codes (the scheduler alerts on anything non-zero):
#   0 ok · 2 bad usage/input · 3 another run holds the lock · 4 screening failed
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
: "${SCREENING_HOME:=$ROOT}"
: "${WATCHLIST:=$SCREENING_HOME/data/watchlist.csv}"
: "${MODEL:=$SCREENING_HOME/data/alert_model.json}"
: "${DB:=$SCREENING_HOME/data/screening.db}"
: "${LOG_DIR:=$SCREENING_HOME/logs}"
: "${LOG_RETENTION_DAYS:=30}"
: "${PYTHON:=python3}"

input="${1:-}"
if [[ -z "$input" || ! -s "$input" ]]; then
  echo "usage: $0 <non-empty customer CSV>" >&2
  exit 2
fi
if ! head -1 "$input" | grep -q '^record_id,name'; then
  echo "unexpected header in $input: $(head -1 "$input")" >&2
  exit 2
fi

mkdir -p "$LOG_DIR"
run_id="$(date -u +%Y%m%dT%H%M%SZ)-$$"
log="$LOG_DIR/screen-$run_id.log"
lock="$LOG_DIR/.screen.lock"

# One run at a time: a second trigger while the first is still writing alerts would
# double-alert every hit. flock is released automatically if this process dies.
exec 9>"$lock"
if ! flock -n 9; then
  echo "another screening run holds $lock" >&2
  exit 3
fi

log() { printf '%s %s\n' "$(date -u +%FT%TZ)" "$*" | tee -a "$log"; }

log "run=$run_id input=$input rows=$(($(wc -l <"$input") - 1)) watchlist=$WATCHLIST"
model_args=()
[[ -f "$MODEL" ]] && model_args=(--model "$MODEL")

if ! (cd "$SCREENING_HOME" && "$PYTHON" -m screening screen \
      --watchlist "$WATCHLIST" --input "$input" --db "$DB" --run-id "$run_id" \
      "${model_args[@]}") >>"$log" 2>&1; then
  log "FAILED — see $log"
  exit 4
fi
log "summary: $(tail -1 "$log")"

find "$LOG_DIR" -name 'screen-*.log' -mtime +"$LOG_RETENTION_DAYS" -delete
log "done"
