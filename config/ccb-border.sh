#!/usr/bin/env bash
# CCB Border Color Script - syncs active pane border from pane metadata

arg="$1"
pane_id=""

if [[ "$arg" == %* ]]; then
  pane_id="$arg"
else
  exit 0
fi

role="$(tmux display-message -p -t "$pane_id" "#{@ccb_role}" 2>/dev/null | tr -d '\r')"
target="$(tmux display-message -p -t "$pane_id" "#{session_name}:#{window_name}" 2>/dev/null | tr -d '\r')"
style=""

if [[ "$role" == "sidebar" && -n "$target" ]]; then
  while IFS=$'\t' read -r pane_role pane_active_style pane_border_style; do
    if [[ "$pane_role" != "sidebar" ]]; then
      style="${pane_active_style:-$pane_border_style}"
    fi
  done < <(tmux list-panes -t "$target" -F '#{@ccb_role}	#{@ccb_active_border_style}	#{@ccb_border_style}' 2>/dev/null || true)
fi

if [[ -z "$style" ]]; then
  style="$(tmux display-message -p -t "$pane_id" "#{@ccb_active_border_style}" 2>/dev/null | tr -d '\r')"
fi
if [[ -z "$style" ]]; then
  style="$(tmux display-message -p -t "$pane_id" "#{@ccb_border_style}" 2>/dev/null | tr -d '\r')"
fi
if [[ -z "$style" ]]; then
  style="fg=#6c7086"
fi

set_border() {
  local style="$1"
  if [[ -n "$pane_id" ]]; then
    # Use set-option -p for pane-level option with pane_id target
    tmux set-option -p -t "$pane_id" pane-active-border-style "$style" 2>/dev/null || \
    tmux set-window-option pane-active-border-style "$style" 2>/dev/null || true
  else
    tmux set-window-option pane-active-border-style "$style" 2>/dev/null || true
  fi
}

set_border "$style"
