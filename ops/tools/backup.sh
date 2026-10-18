#!/bin/bash
# One-way backup of the ops data root to a backup folder (a cloud-synced folder works). The target never writes back.
# Each file is written to a temp name in the target folder and renamed into place, with 3 tries, and one failure never
# stops the others (some FUSE volumes answer EDEADLK to a plain overwrite). Nothing in this file names an account.
#   ops-latest.tar.gz        working tree incl. uncommitted files (no .git)
#   ops-git-history.bundle   full git history (restore: git clone ops-git-history.bundle ops)
#   resume-latest.tar.gz     read-only snapshot of the résumé workspace, if RESUME_DIR is set
#
#   tools/backup.sh            run the backup (schedule it with launchd or cron; run it after every commit if you like)
#   tools/backup.sh --status   last successful backup and its age; exit 1 if older than MAX_AGE_H or never
#                              (09 §4 step 1: the orchestrator runs this at session start)
# Settings (environment, or the same keys in config.toml [paths] read with ops/tools/common.py):
#   JOBHUNT_OPS         data root (default: the ops/ folder of this repo)
#   JOBHUNT_BACKUP_DIR  target folder (required)
#   JOBHUNT_BACKUP_LOG  log file (default ~/Library/Logs/jobhunt-ops-backup.log)
#   JOBHUNT_RESUME_DIR  optional résumé workspace to snapshot read-only
set -uo pipefail
HERE=$(cd "$(dirname "$0")" && pwd)
cfg() { python3 "$HERE/common.py" --get "$1" 2>/dev/null || true; }
SRC="${JOBHUNT_OPS:-$(cfg paths.ops_root)}"; SRC="${SRC:-$(cd "$HERE/.." && pwd)}"
DST="${JOBHUNT_BACKUP_DIR:-$(cfg paths.backup_dir)}"
LOG="${JOBHUNT_BACKUP_LOG:-$(cfg paths.backup_log)}"; LOG="${LOG:-$HOME/Library/Logs/jobhunt-ops-backup.log}"
JH="${JOBHUNT_RESUME_DIR:-}"
[ -n "$DST" ] && [ -d "$DST" ] || { echo "$(date '+%F %T') BACKUP INCOMPLETE: backup folder not set or not found (JOBHUNT_BACKUP_DIR / config paths.backup_dir)" | tee -a "$LOG" >&2; exit 1; }
MAX_AGE_H=36

if [ "${1:-}" = "--status" ]; then
  last=$(grep -E ' ok: ' "$LOG" 2>/dev/null | tail -1 | cut -d' ' -f1,2)
  if [ -z "$last" ]; then echo "backup: no successful run in $LOG"; exit 1; fi
  age=$(( ( $(date +%s) - $(date -j -f '%Y-%m-%d %H:%M:%S' "$last" +%s) ) / 3600 ))
  fails=$(awk -v l="$last" '$0 ~ l {f=1; next} f && /FAIL try|FAILED|deadlock|INCOMPLETE/ {c++} END {print c+0}' "$LOG")
  echo "backup: last success $last (${age} h ago)$( [ "$fails" -gt 0 ] && echo " · $fails failure line(s) since — see $LOG")"
  [ "$age" -le "$MAX_AGE_H" ]; exit $?
fi

TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT
fail=0
put() {  # put <local file> <name in DST>: temp name in the Drive folder, then rename into place; 3 tries
  local src="$1" name="$2" tmp try
  for try in 1 2 3; do
    tmp="$DST/.$name.$$.$try.tmp"   # a fresh temp name per try: a stuck temp file must not turn try 2 into a plain overwrite
    if cat "$src" > "$tmp" 2>/dev/null && mv -f "$tmp" "$DST/$name" 2>/dev/null; then
      return 0
    fi
    rm -f "$tmp" 2>/dev/null
    echo "$(date '+%F %T') FAIL try $try: $name"
    sleep 20
  done
  fail=$((fail+1)); return 1
}
{
  echo "=== $(date '+%F %T') backup start"
  /usr/bin/tar -czf "$TMP/ops.tgz" --exclude .git --exclude .DS_Store -C "$SRC/.." "$(basename "$SRC")" || { echo "tar FAILED"; fail=$((fail+1)); }
  if /usr/bin/git -C "$SRC" rev-parse --git-dir >/dev/null 2>&1; then
    /usr/bin/git -C "$SRC" bundle create "$TMP/ops.bundle" --all >/dev/null 2>&1 || { echo "bundle FAILED"; fail=$((fail+1)); }
  else
    echo "no git repository at $SRC: bundle skipped"
  fi
  [ -s "$TMP/ops.tgz" ] && put "$TMP/ops.tgz" ops-latest.tar.gz
  [ -s "$TMP/ops.bundle" ] && put "$TMP/ops.bundle" ops-git-history.bundle
  true
  if [ -n "$JH" ] && [ -d "$JH" ]; then
    /usr/bin/tar -czf "$TMP/jh.tgz" --exclude .DS_Store --exclude .git -C "$(dirname "$JH")" "$(basename "$JH")" || { echo "resume tar FAILED"; fail=$((fail+1)); }
    [ -s "$TMP/jh.tgz" ] && put "$TMP/jh.tgz" resume-latest.tar.gz
  fi
  if [ "$fail" -eq 0 ]; then
    echo "$(date '+%F %T') ok: tar $(du -h "$TMP/ops.tgz" | cut -f1), bundle $( [ -f "$TMP/ops.bundle" ] && du -h "$TMP/ops.bundle" | cut -f1 || echo none), resume $( [ -f "$TMP/jh.tgz" ] && du -h "$TMP/jh.tgz" | cut -f1 || echo absent)"
  else
    echo "$(date '+%F %T') BACKUP INCOMPLETE: $fail step(s) failed (tar/bundle error, or a target write refused 3 times)"
  fi
} >>"$LOG" 2>&1
