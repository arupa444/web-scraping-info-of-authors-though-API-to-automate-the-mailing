#!/usr/bin/env bash
#
# iceReach control script (macOS / Linux).
#
#   ./run.sh full        Start API + SPA + background worker (daemonised)
#   ./run.sh api         Start only the API/SPA server
#   ./run.sh worker      Start only the background worker
#   ./run.sh status      Show what's running + a /health check
#   ./run.sh logs [api|worker]   Tail logs (both by default)
#   ./run.sh stop        Stop everything this script started
#   ./run.sh restart     Stop, then start full
#   ./run.sh build       Build the React SPA (frontend/dist)
#   ./run.sh migrate     Apply DB migrations (alembic upgrade head)
#   ./run.sh open        Open the app in your browser
#   ./run.sh help        This help
#
# Leading dashes are accepted too:  ./run.sh --full  ==  ./run.sh full
# Override the port:  PORT=9000 ./run.sh full
#
set -euo pipefail
cd "$(dirname "$0")"

PORT="${PORT:-8000}"
PY=".venv/bin/python"
RUN_DIR=".run"
API_PID="$RUN_DIR/api.pid"
WORKER_PID="$RUN_DIR/worker.pid"
API_LOG="$RUN_DIR/api.log"
WORKER_LOG="$RUN_DIR/worker.log"
URL="http://127.0.0.1:$PORT/"
mkdir -p "$RUN_DIR"

c_grn() { printf "\033[32m%s\033[0m\n" "$1"; }
c_red() { printf "\033[31m%s\033[0m\n" "$1"; }
c_dim() { printf "\033[2m%s\033[0m\n" "$1"; }

require_venv() {
  if [ ! -x "$PY" ]; then
    c_red "No .venv found. Create it first:"
    echo "  uv venv && source .venv/bin/activate && uv pip install -r requirements.txt"
    exit 1
  fi
}

# is_running <pidfile> -> 0 if the saved PID is alive
is_running() {
  local f="$1"
  [ -f "$f" ] && kill -0 "$(cat "$f")" 2>/dev/null
}

open_url() {
  if command -v open >/dev/null 2>&1; then open "$URL"
  elif command -v xdg-open >/dev/null 2>&1; then xdg-open "$URL" >/dev/null 2>&1 || true
  fi
}

# Kill whatever is holding $PORT — catches a stale server this script didn't
# start (e.g. an old `python run.py`) so `full` always gets a clean port.
free_port() {
  command -v lsof >/dev/null 2>&1 || return 0
  local pids; pids="$(lsof -ti tcp:"$PORT" 2>/dev/null || true)"
  [ -z "$pids" ] && return 0
  c_dim "Port $PORT busy (pids: $pids) — freeing it."
  kill $pids 2>/dev/null || true
  sleep 1
  pids="$(lsof -ti tcp:"$PORT" 2>/dev/null || true)"
  [ -n "$pids" ] && kill -9 $pids 2>/dev/null || true
}

start_api() {
  require_venv
  if is_running "$API_PID"; then c_dim "API already running (pid $(cat "$API_PID"))."; return; fi
  if [ ! -f frontend/dist/index.html ]; then
    c_dim "frontend/dist not found — building the SPA first…"; build_spa
  fi
  nohup "$PY" -m uvicorn icereach.main:app --app-dir backend --port "$PORT" \
    >"$API_LOG" 2>&1 &
  echo $! >"$API_PID"
  c_grn "API + SPA starting on $URL (pid $(cat "$API_PID"), logs: $API_LOG)"
}

start_worker() {
  require_venv
  if is_running "$WORKER_PID"; then c_dim "Worker already running (pid $(cat "$WORKER_PID"))."; return; fi
  PYTHONPATH="backend${PYTHONPATH:+:$PYTHONPATH}" nohup "$PY" -m icereach.services.queue \
    >"$WORKER_LOG" 2>&1 &
  echo $! >"$WORKER_PID"
  c_grn "Worker starting (pid $(cat "$WORKER_PID"), logs: $WORKER_LOG)"
}

wait_health() {
  printf "Waiting for the API"
  for _ in $(seq 1 30); do
    if curl -fs "${URL}health" >/dev/null 2>&1; then echo " — up."; return 0; fi
    printf "."; sleep 1
  done
  echo; c_red "API did not become healthy — check: ./run.sh logs api"; return 1
}

build_spa() {
  ( cd frontend && npm install --silent && npm run build )
}

cmd_full() {
  # Always start from a clean slate: stop anything we started, then free the
  # port from any stale server before launching.
  cmd_stop
  free_port
  start_api
  start_worker
  wait_health || true
  open_url
  echo
  c_grn "iceReach is up:  $URL"
  c_dim "status: ./run.sh status   logs: ./run.sh logs   stop: ./run.sh stop"
}

cmd_status() {
  local line
  if is_running "$API_PID"; then line="API     RUNNING (pid $(cat "$API_PID"))"; else line="API     stopped"; fi
  echo "$line"
  if is_running "$WORKER_PID"; then line="Worker  RUNNING (pid $(cat "$WORKER_PID"))"; else line="Worker  stopped"; fi
  echo "$line"
  if curl -fs "${URL}health" >/dev/null 2>&1; then
    c_grn "Health  $(curl -fs "${URL}health")"
  else
    c_red "Health  unreachable at ${URL}health"
  fi
}

cmd_logs() {
  local which="${1:-both}"
  case "$which" in
    api)    tail -n 100 -f "$API_LOG" ;;
    worker) tail -n 100 -f "$WORKER_LOG" ;;
    *)      touch "$API_LOG" "$WORKER_LOG"; tail -n 50 -f "$API_LOG" "$WORKER_LOG" ;;
  esac
}

stop_one() {
  local name="$1" f="$2"
  if is_running "$f"; then
    kill "$(cat "$f")" 2>/dev/null || true
    sleep 1
    kill -9 "$(cat "$f")" 2>/dev/null || true
    c_grn "Stopped $name (pid $(cat "$f"))."
  else
    c_dim "$name not running."
  fi
  rm -f "$f"
}

cmd_stop() {
  stop_one "worker" "$WORKER_PID"
  stop_one "API" "$API_PID"
}

usage() { sed -n '3,18p' "$0" | sed 's/^# \{0,1\}//'; }

# ---- dispatch (strip leading dashes) ----
cmd="${1:-help}"; cmd="${cmd#--}"; shift || true
case "$cmd" in
  full)     cmd_full ;;
  api)      start_api; wait_health || true; open_url ;;
  worker)   start_worker ;;
  status)   cmd_status ;;
  logs)     cmd_logs "${1:-both}" ;;
  stop)     cmd_stop ;;
  restart)  cmd_stop; sleep 1; cmd_full ;;
  build)    build_spa ;;
  migrate)  require_venv; DATABASE_URL="${DATABASE_URL:-sqlite:///./icereach.db}" \
              "$PY" -m alembic -c backend/alembic.ini upgrade head ;;
  open)     open_url ;;
  help|"")  usage ;;
  *)        c_red "Unknown command: $cmd"; echo; usage; exit 1 ;;
esac
