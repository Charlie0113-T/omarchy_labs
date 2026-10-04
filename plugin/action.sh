#!/bin/bash
# Actions behind the Omarchy Lab bar widget.
#
# Usage: bash plugin/action.sh <action> [language]
#   typical | daily | agent | agent-live   run a test in a visible terminal
#   status                                 print "running" or "idle"
#   stop                                   stop the running test (it still saves a report)
#   open-report | open-folder | share      use the latest results
#
# Nothing here runs on install, enable or shell start: every test starts only
# when the user picks it, and always in a terminal they can see and close.

set -uo pipefail

ROOT=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)
SRC="$ROOT/src"
REPORTS="$HOME/omarchy-lab"
ACTION="${1:-}"
LANGUAGE="${2:-en}"

say() {
  case "$LANGUAGE:$1" in
  zh-CN:live) echo "此测试会调用你配置的模型并消耗额度。按回车开始，按 Ctrl+C 取消。" ;;
  zh-TW:live) echo "此測試會呼叫你設定的模型並消耗額度。按 Enter 開始，按 Ctrl+C 取消。" ;;
  ja:live) echo "このテストは設定済みのモデルを呼び出し、利用枠を消費します。Enter で開始、Ctrl+C で取り消します。" ;;
  *:live) echo "This test calls your configured model and uses your quota. Press Enter to start, or Ctrl+C to cancel." ;;
  zh-CN:none) echo "还没有测试结果，请先运行一项测试。" ;;
  zh-TW:none) echo "還沒有測試結果，請先執行一項測試。" ;;
  ja:none) echo "まだ結果がありません。先にテストを実行してください。" ;;
  *:none) echo "No results yet. Run a test first." ;;
  zh-CN:copied) echo "Issue 正文已复制。粘贴到打开的页面，检查后再提交。" ;;
  zh-TW:copied) echo "Issue 內文已複製。貼到開啟的頁面，檢查後再送出。" ;;
  ja:copied) echo "Issue の本文をコピーしました。開いたページに貼り付け、確認してから送信してください。" ;;
  *:copied) echo "Issue text copied. Paste it into the page that opened, review it, then submit." ;;
  zh-CN:no-issue) echo "最近一次测试没有可分享的 issue.md。" ;;
  zh-TW:no-issue) echo "最近一次測試沒有可分享的 issue.md。" ;;
  ja:no-issue) echo "最新の実行には共有できる issue.md がありません。" ;;
  *:no-issue) echo "The latest run has no issue.md to share." ;;
  esac
}

notify() {
  notify-send -a "Omarchy Lab" "Omarchy Lab" "$1" 2>/dev/null || true
}

latest_run() {
  # Report directories start with a timestamp, so the last one by name is the newest.
  find "$REPORTS" -mindepth 1 -maxdepth 1 -type d -name '2*' 2>/dev/null | sort | tail -n 1
}

test_pids() {
  # A test is "python3 -B <plugin>/src <mode>"; match that argument exactly,
  # never just a name, so no other process can be signalled.
  local pid
  for pid in $(pgrep -u "$(id -u)" -f -- "$SRC" 2>/dev/null); do
    if tr '\0' '\n' <"/proc/$pid/cmdline" 2>/dev/null | grep -qxF -- "$SRC"; then
      echo "$pid"
    fi
  done
}

quote() {
  # Single-quote for bash -c; unlike printf %q it never splits multibyte text.
  local escaped=${1//\'/\'\\\'\'}
  printf "'%s'" "$escaped"
}

run_in_terminal() {
  # -B and PYTHONDONTWRITEBYTECODE keep the plugin checkout free of cache files.
  local command
  command="PYTHONDONTWRITEBYTECODE=1 python3 -B $(quote "$SRC") $1"
  if [[ ${2:-} == confirm ]]; then
    command="printf '%s\n' $(quote "$(say live)"); read -r _ && $command"
  fi
  exec omarchy-launch-floating-terminal-with-presentation "$command"
}

case "$ACTION" in
typical | daily | agent)
  run_in_terminal "$ACTION"
  ;;
agent-live)
  run_in_terminal "agent --live" confirm
  ;;
status)
  if [[ -n $(test_pids) ]]; then echo running; else echo idle; fi
  ;;
stop)
  pids=$(test_pids)
  # SIGTERM takes the same path as Ctrl+C: the browser and temporary files are
  # cleaned up and a partial report is saved.
  [[ -z $pids ]] || kill -TERM $pids
  ;;
open-report)
  dir=$(latest_run)
  if [[ -z $dir || ! -f $dir/report.txt ]]; then
    notify "$(say none)"
    exit 0
  fi
  exec omarchy-launch-editor "$dir/report.txt"
  ;;
open-folder)
  if [[ ! -d $REPORTS ]]; then
    notify "$(say none)"
    exit 0
  fi
  exec xdg-open "$REPORTS"
  ;;
share)
  dir=$(latest_run)
  if [[ -z $dir || ! -f $dir/issue.md || ! -f $dir/issue-url.txt ]]; then
    notify "$(say no-issue)"
    exit 0
  fi
  if command -v wl-copy >/dev/null; then
    wl-copy <"$dir/issue.md"
    notify "$(say copied)"
  else
    omarchy-launch-editor "$dir/issue.md" &
  fi
  exec xdg-open "$(head -n 1 "$dir/issue-url.txt")"
  ;;
*)
  echo "usage: action.sh typical|daily|agent|agent-live|status|stop|open-report|open-folder|share [language]" >&2
  exit 2
  ;;
esac
