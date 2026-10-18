#!/bin/zsh
# Which Chrome windows can a lane actually use? Read-only window check + a one-lane-at-a-time start gate
# (09 §2 rule 2, §4 step 9 and lane step 3). Changes nothing: no clicks, no window moves. macOS only (osascript/JXA).
#
# Why: when five lanes once started within a minute, their tab groups landed as background tabs inside shared
# windows (a background tab is always visibilityState "hidden", and Chrome froze them: 45 s JS timeouts), and the
# windows that did exist were near-full-screen and stacked, some fully covered by other apps. A plain window list
# couldn't show either problem: it lists windows, not tabs, and ignores other apps' windows.
#
# The lane tab is recognised by its host, LANE_TAB_HOST (default example.com; config [browser] lane_tab_url).
#
#   tools/lane-windows.sh                      report: every Chrome window front to back, how much of it shows on screen
#                                              (other apps' windows count as cover), its tabs by host, and a verdict
#   tools/lane-windows.sh --ids                print the current Chrome window ids (the baseline for --wait-new)
#   tools/lane-windows.sh --lane-tab           where is the lane's example.com tab (09 §4 lane step 4)? prints
#                                              `LANE TAB: window <id> · alone · VISIBLE …` (exit 0) or `… SHARED with <n> other tabs`
#                                              / `not found` / `NOT showing` (exit 1). `dispatch.py register` runs it and prints the result.
#   tools/lane-windows.sh --wait-new "<ids>" [--timeout <s>]
#                                              the start gate: wait for ONE Chrome window that isn't in <ids> (the lane
#                                              just started opened it), let it settle 5 s, then PASS only if it has exactly
#                                              one tab and part of it shows on screen. Exit 0 PASS · 1 FAIL · 3 timeout.
#
# Orchestrator use (one lane at a time):  ids=$(tools/lane-windows.sh --ids) → give the operator lane N's line →
#   tools/lane-windows.sh --wait-new "$ids" --timeout 600 (Bash run_in_background) → PASS: say so and give the next lane's
#   line (never tile or move windows: the operator arranges them, 09 v2.8 §2 rule 4) · FAIL: tell the operator what it shows before any lane clicks.
# Visibility is sampled every 10 pt, so a sliver under ~10 pt reads as covered. macOS only needs one visible pixel, so
# this errs toward "covered".
# Needs the macOS Automation permission for Chrome (System Settings → Privacy & Security → Automation). The window list needs no Screen Recording permission.
set -e
MODE=report IDS="" TIMEOUT=600
LANE_TAB_HOST="${JOBHUNT_LANE_TAB_HOST:-example.com}"
while [[ $# -gt 0 ]]; do
  case "$1" in
    --ids) MODE=ids ;;
    --lane-tab) MODE=lanetab ;;
    --wait-new) MODE=wait; IDS="$2"; shift ;;
    --timeout) TIMEOUT="$2"; shift ;;
    -h|--help) sed -n '2,27p' "$0"; exit 0 ;;
    *) echo "unknown argument: $1 (see --help)"; exit 2 ;;
  esac
  shift
done

jxa() {  # $1 = report | ids | one:<id>
  osascript -l JavaScript - "$1" "$LANE_TAB_HOST" <<'JXA'
function run(argv) {
  ObjC.import('AppKit'); ObjC.import('CoreGraphics');
  const mode = argv[0], laneHost = argv[1] || 'example.com';
  const chrome = Application('Google Chrome');
  const host = u => { const m = /^[a-z-]+:\/\/([^/?#]*)/i.exec(u || ''); return m ? m[1] || u.split(':')[0] : (u || '?'); };
  const wins = chrome.windows().map(w => {
    let b = w.bounds(), tabs = [];
    try { tabs = w.tabs().map(t => host(t.url())); } catch (e) {}
    return {id: w.id(), min: w.minimized(), b: [b.x, b.y, b.width, b.height], tabs, active: w.activeTabIndex()};
  });
  if (mode === 'ids') return wins.map(w => w.id).join(' ');
  // On-screen windows of every app, front to back (layer 0 = normal windows).
  const cg = ObjC.deepUnwrap(ObjC.castRefToObject($.CGWindowListCopyWindowInfo(
    $.kCGWindowListOptionOnScreenOnly | $.kCGWindowListExcludeDesktopElements, $.kCGNullWindowID)))
    .filter(w => w.kCGWindowLayer === 0 && w.kCGWindowAlpha > 0 && w.kCGWindowBounds.Width > 40 && w.kCGWindowBounds.Height > 40)
    .map(w => ({owner: w.kCGWindowOwnerName, r: [w.kCGWindowBounds.X, w.kCGWindowBounds.Y, w.kCGWindowBounds.Width, w.kCGWindowBounds.Height]}));
  // Screens, converted to top-left coordinates.
  const H0 = $.NSScreen.screens.objectAtIndex(0).frame.size.height;
  const screens = [];
  for (let i = 0; i < $.NSScreen.screens.count; i++) {
    const f = $.NSScreen.screens.objectAtIndex(i).frame;
    screens.push([f.origin.x, H0 - (f.origin.y + f.size.height), f.size.width, f.size.height]);
  }
  const inR = (x, y, r) => x >= r[0] && x < r[0] + r[2] && y >= r[1] && y < r[1] + r[3];
  const same = (a, b) => a.every((v, i) => Math.abs(v - b[i]) < 1);
  const used = new Set();
  const out = wins.map(w => {
    const k = cg.findIndex((c, i) => !used.has(i) && c.owner === 'Google Chrome' && same(c.r, w.b));
    let verdict, pct = 0, cover = [];
    if (w.min) verdict = 'MINIMIZED';
    else if (k < 0) verdict = 'NOT ON SCREEN (another Space, or behind a full-screen app)';
    else {
      used.add(k);
      const front = cg.slice(0, k), r = w.b, step = 10;
      let tot = 0, vis = 0;
      for (let x = r[0] + step / 2; x < r[0] + r[2]; x += step)
        for (let y = r[1] + step / 2; y < r[1] + r[3]; y += step) {
          tot++;
          if (!screens.some(s => inR(x, y, s))) continue;
          if (!front.some(f => inR(x, y, f.r))) vis++;
        }
      pct = tot ? Math.round(100 * vis / tot) : 0;
      cover = [...new Set(front.filter(f => f.owner !== 'Google Chrome').map(f => f.owner))];
      verdict = vis ? `VISIBLE ${pct < 1 ? '<1' : pct}% showing` : 'COVERED (0% showing: pages report hidden)';
    }
    return {id: w.id, verdict, visible: !w.min && k >= 0 && (pct > 0 || verdict.startsWith('VISIBLE')),
            ntabs: w.tabs.length, active: w.tabs[w.active - 1] || '?', tabs: w.tabs, b: w.b, cover};
  });
  if (mode === 'lanetab') {
    const lt = out.filter(o => o.tabs.includes(laneHost));
    return JSON.stringify(lt.map(o => ({id: o.id, ntabs: o.ntabs, visible: o.visible, verdict: o.verdict})));
  }
  if (mode.startsWith('one:')) {
    const w = out.find(o => String(o.id) === mode.slice(4));
    return w ? JSON.stringify(w) : '';
  }
  const lines = ['CHROME WINDOWS (front to back; % = share of the window not covered by any window in front of it)'];
  out.forEach((w, i) => {
    let l = `${i + 1}. id ${w.id} · ${w.verdict} · ${w.ntabs} tab${w.ntabs === 1 ? '' : 's'} · front tab: ${w.active}`;
    if (w.tabs.includes(laneHost)) l += w.ntabs > 1 ? `\n     ⚑ holds a lane's ${laneHost} tab and ${w.ntabs - 1} other tab(s): that lane's window proof fails` : `\n     ⚑ a lane's ${laneHost} tab, alone`;
    if (w.ntabs > 1) l += `\n     tabs: ${w.tabs.join(', ')}\n     ⚠ several tabs: a lane tab that isn't the front tab is a background tab (hidden, may freeze)`;
    if (w.cover.length) l += `\n     covered in part by: ${w.cover.join(', ')}`;
    lines.push(l);
  });
  const shared = out.filter(w => w.ntabs > 1).length;
  lines.push(`${out.length} Chrome window(s) · ${out.filter(w => w.visible).length} showing · ${out.filter(w => !w.visible).length} hidden · ${shared} with several tabs`);
  return lines.join('\n');
}
JXA
}

power() {
  local b; b=$(pmset -g batt | sed -n 2p | sed -E 's/.*\t//; s/;.*present.*//')
  pmset -g batt | head -1 | grep -q 'AC Power' && echo "Power: AC · $b" || echo "Power: BATTERY · $b (plug in: Chrome throttles background pages harder on battery)"
  pmset -g assertions | grep -q 'PreventUserIdleDisplaySleep *1' && echo "Display sleep: prevented" || echo "Display sleep: NOT prevented (turn on Caffeine, 09 §2)"
}

case $MODE in
  ids) jxa ids ;;
  report) jxa report; power ;;
  lanetab)
    r=$(jxa lanetab 2>/dev/null) || { echo "LANE TAB: can't read Chrome (not running, or Automation permission denied)"; exit 2; }
    python3 - "$r" <<'PY'
import json, sys
ws = json.loads(sys.argv[1] or '[]')
if not ws:
    print('LANE TAB: not found (no Chrome window has the lane tab)'); sys.exit(1)
rc = 0
for w in ws:
    if w['ntabs'] != 1:
        print(f"LANE TAB: window {w['id']} · SHARED with {w['ntabs'] - 1} other tab(s): the lane's tab is a background tab there. the operator moves it (he manages windows)."); rc = 1
    elif not w['visible']:
        print(f"LANE TAB: window {w['id']} · alone but NOT showing ({w['verdict']})"); rc = 1
    else:
        print(f"LANE TAB: window {w['id']} · alone · {w['verdict']}")
sys.exit(rc)
PY
    ;;
  wait)
    [[ -n "$IDS" ]] || { echo "--wait-new needs the baseline ids from --ids"; exit 2; }
    jxa ids >/dev/null 2>&1 || { echo "GATE ERROR · can't read Chrome's windows (Chrome not running, or Automation permission denied: System Settings → Privacy & Security → Automation)"; exit 2; }
    base=(${=IDS}); end=$((SECONDS + TIMEOUT)); new=()
    while (( SECONDS < end )); do
      new=()
      for i in ${=$(jxa ids)}; do (( ${base[(Ie)$i]} )) || new+=$i; done
      (( ${#new} )) && break
      sleep 2
    done
    (( ${#new} )) || { echo "GATE TIMEOUT · no new Chrome window in ${TIMEOUT}s: the lane hasn't opened one, or its tab group went into an existing window (run with no arguments to look)"; exit 3; }
    sleep 5
    now=(${=$(jxa ids)}); new=(); for i in $now; do (( ${base[(Ie)$i]} )) || new+=$i; done
    (( ${#new} == 1 )) || { echo "GATE FAIL · ${#new} new Chrome windows (${new}); expected exactly one for this lane"; jxa report; exit 1; }
    w=$(jxa "one:${new[1]}")
    python3 - "$w" <<'PY'
import json, sys
w = json.loads(sys.argv[1])
bad = []
if w['ntabs'] != 1: bad.append(f"{w['ntabs']} tabs ({', '.join(w['tabs'])}): the lane's tab must be alone in its window")
if not w['visible']: bad.append('not showing on screen: the lane\'s page reports hidden and its clicks are lost')
print(('GATE PASS' if not bad else 'GATE FAIL') + f" · new window id {w['id']} · front tab {w['active']} · {w['verdict']}"
      + ('' if not bad else ' · ' + ' · '.join(bad)))
sys.exit(1 if bad else 0)
PY
    ;;
esac
