#!/bin/sh
# run_agent.sh — launch an agent command, show progress, kill on Ctrl+C or timeout
#
# Usage:
#   run_agent.sh <label> <logfile> <timeout_secs> <success_test_expr> -- <cmd> [args...]
#
#   label              e.g. "catalog" — appears in progress lines
#   logfile            path to write agent stdout+stderr
#   timeout_secs       hard kill deadline in seconds
#   success_test_expr  shell test fragment evaluated after agent exits,
#                      e.g. '-f /path/to/catalog.json'
#   --                 separator before the agent command
#   cmd [args...]      the agent command + prompt
#
# Exit codes:
#   0  agent finished and success_test_expr is true
#   1  interrupted, timed out, or success_test_expr is false

LABEL="$1";    shift
LOGFILE="$1";  shift
TIMEOUT="$1";  shift
SUCCESS="$1";  shift
shift  # consume '--'

START=$(date +%s)
DEADLINE=$(( START + TIMEOUT ))
DEADLINE_STR=$(date -d @$DEADLINE '+%H:%M:%S' 2>/dev/null \
            || date -r  $DEADLINE '+%H:%M:%S' 2>/dev/null \
            || echo "n/a")
TIMEOUT_MIN=$(( TIMEOUT / 60 ))

echo "  started : $(date '+%H:%M:%S')"
echo "  log     : $LOGFILE"
echo "  timeout : ${TIMEOUT_MIN} min  (deadline $DEADLINE_STR)"
echo ""

# Locate scrape_progress.py next to this script
SCRIPT_DIR=$(cd "$(dirname "$0")" && pwd)
SCRAPER="$SCRIPT_DIR/scrape_progress.py"

# Launch agent in background, output to log only (silent)
"$@" > "$LOGFILE" 2>&1 &
AGENT_PID=$!

# Trap Ctrl+C / SIGTERM: kill agent and exit
trap '
    echo ""
    echo "  [$LABEL] interrupted — killing agent (PID $AGENT_PID) ..."
    kill $AGENT_PID 2>/dev/null
    wait $AGENT_PID 2>/dev/null
    echo "  [$LABEL] stopped."
    exit 1
' INT TERM

# Progress monitor
while kill -0 $AGENT_PID 2>/dev/null; do
    sleep 60
    kill -0 $AGENT_PID 2>/dev/null || break

    NOW=$(date +%s)
    ELAPSED=$(( NOW - START ))
    REMAINING=$(( DEADLINE - NOW ))
    ELAPSED_MIN=$(( ELAPSED / 60 ))
    ELAPSED_SEC=$(( ELAPSED % 60 ))

    if [ $REMAINING -le 0 ]; then
        echo ""
        echo "  [$LABEL] TIMEOUT after ${ELAPSED_MIN}m${ELAPSED_SEC}s — killing agent"
        kill $AGENT_PID 2>/dev/null
        wait $AGENT_PID 2>/dev/null
        echo "  Check $LOGFILE for details."
        exit 1
    fi

    REMAINING_MIN=$(( REMAINING / 60 ))
    if [ -f "$SCRAPER" ]; then
        ACTIVITY=$(python3 "$SCRAPER" "$LOGFILE" 2>/dev/null | head -1 || echo "")
    else
        ACTIVITY=""
    fi
    if [ -n "$ACTIVITY" ]; then
        printf "  [$LABEL] %dm%02ds | %d min left | %s\n" \
            $ELAPSED_MIN $ELAPSED_SEC $REMAINING_MIN "$ACTIVITY"
    else
        printf "  [$LABEL] elapsed %dm%02ds  |  deadline $DEADLINE_STR  |  %d min remaining\n" \
            $ELAPSED_MIN $ELAPSED_SEC $REMAINING_MIN
    fi
done

trap '' INT TERM
wait $AGENT_PID 2>/dev/null || true

ELAPSED=$(( $(date +%s) - START ))
echo ""
echo "  [$LABEL] finished in $(( ELAPSED / 60 ))m$(( ELAPSED % 60 ))s"

# Print cost summary if available
if [ -f "$SCRAPER" ]; then
    COST=$(python3 "$SCRAPER" "$LOGFILE" --cost 2>/dev/null || echo "")
    [ -n "$COST" ] && echo "  [$LABEL] cost: $COST"
fi
echo ""

# Check success condition
if eval "[ $SUCCESS ]"; then
    exit 0
else
    echo "  [$LABEL] ERROR: expected output not found — check $LOGFILE"
    exit 1
fi
