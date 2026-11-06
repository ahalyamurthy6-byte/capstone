#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"
mkdir -p logs

start_server() {
  local name="$1"
  local port="$2"
  local module="$3"
  local log_path="logs/${name}.log"
  local pid_path="logs/${name}.pid"

  if [[ -f "$pid_path" ]]; then
    local pid
    pid="$(cat "$pid_path" 2>/dev/null || true)"
    if [[ -n "$pid" ]] && kill -0 "$pid" 2>/dev/null; then
      echo "$name already running (pid $pid)"
      return 0
    fi
    rm -f "$pid_path"
  fi

  MCP_TRANSPORT=streamable-http PYTHONPATH="$ROOT_DIR" .venv/bin/python -m "$module" >"$log_path" 2>&1 &
  local pid=$!
  echo "$pid" > "$pid_path"

  local deadline=$((SECONDS + 60))
  while (( SECONDS < deadline )); do
    if python - "$port" <<'PY'
import socket, sys
port = int(sys.argv[1])
try:
    with socket.create_connection(("127.0.0.1", port), timeout=1):
        raise SystemExit(0)
except OSError:
    raise SystemExit(1)
PY
    then
      break
    fi
    sleep 1
  done

  if ! python - "$port" <<'PY'
import socket, sys
port = int(sys.argv[1])
try:
    with socket.create_connection(("127.0.0.1", port), timeout=1):
        raise SystemExit(0)
except OSError:
    raise SystemExit(1)
PY
  then
    echo "Timed out waiting for $name on port $port" >&2
    exit 1
  fi

  echo "$name ready on port $port"
}

start_server case 8001 mcp_servers.case.server
start_server policy 8002 mcp_servers.policy.server
start_server documents 8003 mcp_servers.documents.server
start_server workflow 8004 mcp_servers.workflow.server

printf 'case-mcp http://localhost:8001/mcp\n'
printf 'policy-mcp http://localhost:8002/mcp\n'
printf 'documents-mcp http://localhost:8003/mcp\n'
printf 'workflow-mcp http://localhost:8004/mcp\n'
