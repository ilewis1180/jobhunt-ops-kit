#!/bin/zsh
# backup-watchdog.sh — alert when no successful ops backup in MAX_HOURS (default 36).
#
# Why this exists, separately from backup.sh: once the scheduled backup hit a cloud-drive FUSE
# deadlock, no other trigger compensated, and there was ZERO successful backup that day.
# Nothing reported it. A check that lives inside the backup script cannot catch the case
# where the backup never runs — so this is deliberately a separate job with its own schedule.
#
# It reads the backup's own log and looks for the most recent " ok: " line, which
# backup.sh writes only after every step succeeded. Missing log, unreadable log
# and no-ok-line-ever all count as failure: fail loud, never silently pass.
#
# Exit 0 = healthy, 1 = stale or unknown (and a notification was raised).

set -u
LOG="${JOBHUNT_BACKUP_LOG:-$HOME/Library/Logs/jobhunt-ops-backup.log}"
STATE="$HOME/Library/Logs/jobhunt-backup-watchdog.log"
MAX_HOURS="${JOBHUNT_BACKUP_MAX_HOURS:-36}"

note() { print -r -- "$(date '+%F %T') $*" >> "$STATE"; }

alert() {   # on-screen, and in the log. No network, no credentials.
  local msg="$1"
  note "ALERT: $msg"
  /usr/bin/osascript -e "display notification \"$msg\" with title \"JobHunt backup\" sound name \"Basso\"" 2>/dev/null
  print -r -- "JobHunt backup: $msg"
}

if [ ! -r "$LOG" ]; then
  alert "no backup log at $LOG — cannot tell whether a backup has ever run"
  exit 1
fi

# backup.sh writes:  2026-10-10 04:30:09 ok: tar 14M, bundle 8.0M, ...
last_ok=$(/usr/bin/grep ' ok: ' "$LOG" 2>/dev/null | /usr/bin/tail -1)
if [ -z "$last_ok" ]; then
  alert "backup log exists but records no successful run"
  exit 1
fi

stamp="${last_ok%% ok:*}"
last_epoch=$(/bin/date -j -f '%Y-%m-%d %H:%M:%S' "$stamp" '+%s' 2>/dev/null)
if [ -z "$last_epoch" ]; then
  alert "could not parse the last success timestamp (${stamp}) — treating as unknown"
  exit 1
fi

age_h=$(( ( $(/bin/date '+%s') - last_epoch ) / 3600 ))
if [ "$age_h" -ge "$MAX_HOURS" ]; then
  alert "no successful backup in ${age_h}h (limit ${MAX_HOURS}h). Last good: $stamp"
  exit 1
fi

note "ok: last successful backup ${age_h}h ago ($stamp)"
exit 0
