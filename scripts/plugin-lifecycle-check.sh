#!/bin/bash
# Check the Omarchy Lab plugin's whole lifecycle on a real Omarchy (Quattro) desktop:
# install -> validate -> nothing auto-starts -> enable -> panel -> run -> stop ->
# close terminal -> disable -> re-enable -> remove.
#
# Usage (as your normal user, inside the desktop session):
#   bash scripts/plugin-lifecycle-check.sh                 # install from the default branch
#   bash scripts/plugin-lifecycle-check.sh --branch NAME   # hand-install a branch, e.g. before merging
#
# It uses only the documented `omarchy plugin` commands. It asks before steps that
# open windows and when it needs your eyes. A short local replay and two
# interrupted daily runs are the only tests it starts; no model is called.
# At the end the plugin is removed again. A log is saved for pasting into the PR.

set -uo pipefail

URL="${OMARCHY_LAB_URL:-https://github.com/Charlie0113-T/omarchy_labs}"  # override to test a fork
ID="io.github.charlie0113-t.omarchy-lab"
DIR="$HOME/.config/omarchy/plugins/$ID"
REPORTS="$HOME/omarchy-lab"
SHELL_JSON="$HOME/.config/omarchy/shell.json"
LOG="$HOME/omarchy-lab-plugin-check-$(date +%Y%m%d-%H%M%S).txt"
BRANCH=""
RESULTS=()

[[ ${1:-} == --branch ]] && BRANCH="${2:?--branch needs a name}"

say() { printf '%s\n' "$*" | tee -a "$LOG"; }
record() {
  RESULTS+=("$1|$2|$3")
  say "  [$1] $2${3:+ — $3}"
}
check() { # check "<name>" <command...>
  local name="$1"
  shift
  if "$@" >>"$LOG" 2>&1; then record PASS "$name" ""; else record FAIL "$name" "see log"; fi
}
ask() { # ask "<question>" -> PASS/FAIL from the user's answer
  local answer
  # Drop keys pressed while waiting (e.g. Enter) so they cannot answer this question.
  while read -r -t 0.1 -n 1000 _ </dev/tty; do :; done
  while true; do
    read -r -p "  ? $1 [y/n] " answer </dev/tty || answer=n
    case $answer in
    [yY]*) record PASS "$1" "confirmed by you"; return ;;
    [nN]*) record FAIL "$1" "you answered no"; return ;;
    esac
  done
}
wait_for() { # wait_for <seconds> <command...>
  local seconds="$1"
  shift
  for ((i = 0; i < seconds; i++)); do
    "$@" >/dev/null 2>&1 && return 0
    sleep 1
  done
  return 1
}
plugin_state() { omarchy plugin list --json | jq -r --arg id "$ID" '(.[] | select(.id == $id) | if .enabled then "enabled" else "disabled" end) // "absent"'; }
state_is() { [[ $(plugin_state) == "$1" ]]; }
in_shell_json() { [[ -f $SHELL_JSON ]] && grep -qF "\"$ID\"" "$SHELL_JSON"; }
not_in_shell_json() { ! in_shell_json; }
action() { bash "$DIR/plugin/action.sh" "$@"; }
# Like the bar widget, start tests detached: the terminal launcher may not return until its window closes.
launch() { (bash "$DIR/plugin/action.sh" "$@" >>"$LOG" 2>&1 &); }
idle() { [[ $(action status) == idle ]]; }
running() { [[ $(action status) == running ]]; }
run_count() { find "$REPORTS" -mindepth 1 -maxdepth 1 -type d -name '2*' 2>/dev/null | wc -l; }
latest_run() { find "$REPORTS" -mindepth 1 -maxdepth 1 -type d -name '2*' 2>/dev/null | sort | tail -n 1; }
latest_status_is() {
  local d
  d=$(latest_run)
  grep -q "\"status\": \"$1\"" "$d/results.json" && return 0
  # Keep what the run actually left behind, for diagnosis.
  echo "latest run $d contains: $(ls "$d" 2>&1 | tr '\n' ' ')"
  grep -m1 '"status"' "$d/results.json"
  return 1
}
latest_has_share_files() { local d; d=$(latest_run); [[ -f $d/report.txt && -f $d/issue.md && -f $d/issue-url.txt ]]; }
test_browsers() {
  local pid n=0
  for pid in $(pgrep -u "$(id -u)" -f bench-browser-profile- 2>/dev/null); do
    tr '\0' '\n' <"/proc/$pid/cmdline" 2>/dev/null | grep -q -- '--user-data-dir=.*bench-browser-profile-' && n=$((n + 1))
  done
  echo "$n"
}
no_test_browsers() { [[ $(test_browsers) -eq 0 ]]; }
has_test_browsers() { [[ $(test_browsers) -gt 0 ]]; }
no_temp_dirs() { ! compgen -G "$HOME/.omarchy-lab-*" >/dev/null && ! compgen -G "$HOME/.omarchy-update-load-*" >/dev/null; }
start_daily_and_wait_for_browser() {
  launch daily en
  wait_for 120 running && wait_for 120 has_test_browsers && sleep 5
}

say "Omarchy Lab plugin lifecycle check — $(date)"
say "Log: $LOG"
say ""

# 0. Preconditions
say "0. Preconditions"
for cmd in omarchy omarchy-shell jq git python3; do
  command -v "$cmd" >/dev/null || { say "  missing command: $cmd"; exit 1; }
done
omarchy-shell shell ping >/dev/null 2>&1 || { say "  omarchy-shell is not running; run this inside the desktop session"; exit 1; }
if [[ -e $DIR ]] || ! state_is absent; then
  say "  $ID is already installed. Remove it first: omarchy plugin remove $ID"
  exit 1
fi
command -v fio >/dev/null && command -v sysbench >/dev/null || say "  note: fio/sysbench missing; only the typical test needs them"
say "  python3 $(python3 -V 2>&1 | cut -d' ' -f2), $(omarchy-version 2>/dev/null || echo 'omarchy version unknown')"
runs_before=$(run_count)

# 1. Install
if [[ -n $BRANCH ]]; then
  say "1. Install branch $BRANCH by hand (clone into the plugins folder, then rescan)"
  check "clone branch $BRANCH into the plugins folder" git clone -q --branch "$BRANCH" "$URL" "$DIR"
  check "omarchy-shell rescans plugins" omarchy-shell shell rescanPlugins
else
  say "1. Install with omarchy plugin add"
  check "omarchy plugin add" omarchy plugin add "$URL" --yes
fi
check "plugin is discovered and starts disabled" wait_for 10 state_is disabled

# 2. Validate
say "2. Validate"
check "omarchy plugin validate" omarchy plugin validate "$DIR"

# 3. Nothing runs by itself
say "3. Nothing starts on install"
check "no test process after install" idle
check "no new results after install" test "$(run_count)" -eq "$runs_before"

# 4. Enable
say "4. Enable"
check "omarchy plugin enable" omarchy plugin enable "$ID" --section right
check "plugin is enabled" wait_for 10 state_is enabled
check "bar entry written to shell.json" in_shell_json
check "still no test process after enable" idle
check "still no new results after enable" test "$(run_count)" -eq "$runs_before"
ask "Is the flask icon in the right side of your bar?"

# 5. Panel
say "5. Panel"
omarchy-shell "$ID" open >>"$LOG" 2>&1
ask "Did a panel open with Run a test (4 items) and Results (3 items)?"
omarchy-shell "$ID" close >>"$LOG" 2>&1

# 6. Run a short test from the plugin
say "6. Run: Agent local replay (about 1 minute, no model)"
say "  A terminal opens. Pick a language there, then wait for 'Done'."
launch agent en
check "test starts in a terminal" wait_for 60 running
check "test finishes" wait_for 600 idle
check "results saved with issue.md and issue-url.txt" latest_has_share_files
check "run completed" latest_status_is COMPLETE
say "  Press any key in that terminal to close it."
ask "Did the terminal show the report and the 'Share this result' steps?"

# 7. Stop from the plugin
say "7. Stop: Daily, then the panel's Stop action"
say "  A terminal and a Chromium test window open. Pick a language; the script stops it."
if start_daily_and_wait_for_browser; then
  record PASS "daily test started its browser" ""
  action stop
  check "test stops" wait_for 60 idle
  check "test browser closed" wait_for 15 no_test_browsers
  check "temporary folders cleaned up" no_temp_dirs
  check "partial results saved as INTERRUPTED" latest_status_is INTERRUPTED
else
  record FAIL "daily test started its browser" "no Chromium test window within 4 minutes"
  action stop
fi
say "  Press any key in that terminal to close it."

# 8. Close the terminal mid-test
say "8. Close the terminal mid-test"
if start_daily_and_wait_for_browser; then
  record PASS "daily test started its browser" ""
  say "  Now close the Omarchy Lab terminal window (not this one), e.g. with Super+W."
  check "test stops when its terminal closes" wait_for 120 idle
  check "test browser closed" wait_for 15 no_test_browsers
  check "temporary folders cleaned up" no_temp_dirs
  check "partial results saved as INTERRUPTED" latest_status_is INTERRUPTED
else
  record FAIL "daily test started its browser" "no Chromium test window within 4 minutes"
  action stop
fi

# 9. Disable and re-enable
say "9. Disable and re-enable"
check "omarchy plugin disable" omarchy plugin disable "$ID"
check "plugin is disabled" wait_for 10 state_is disabled
check "bar entry removed from shell.json" not_in_shell_json
ask "Is the flask icon gone from the bar?"
check "omarchy plugin enable again" omarchy plugin enable "$ID" --section right
check "plugin is enabled again" wait_for 10 state_is enabled

# 10. Remove
say "10. Remove"
check "omarchy plugin remove" omarchy plugin remove "$ID" --yes
check "plugin folder deleted" test ! -e "$DIR"
check "plugin no longer listed" wait_for 10 state_is absent
check "no bar entry left in shell.json" not_in_shell_json
check "results stay in ~/omarchy-lab" test -d "$REPORTS"

# Summary
pass=0 fail=0
say ""
say "Summary"
for row in "${RESULTS[@]}"; do
  IFS='|' read -r status name note <<<"$row"
  [[ $status == PASS ]] && pass=$((pass + 1)) || fail=$((fail + 1))
  say "| $status | $name |${note:+ $note}"
done
say ""
say "$pass passed, $fail failed. Paste $LOG into the pull request."
((fail == 0))
