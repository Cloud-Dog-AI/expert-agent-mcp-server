#!/bin/bash
# Copyright 2026 Cloud-Dog, Viewdeck Engineering Limited
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.


# Expert Agent MCP Server Control Script
# Reads configuration from env/defaults.yaml

# Script directory
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SELF_PATH="$SCRIPT_DIR/$(basename "${BASH_SOURCE[0]}")"
cd "$SCRIPT_DIR"

# Optional: explicit env file for config (RULES.md)
# Usage: ./server_control.sh --env private/env-test start api
ENV_FILE=""
POSITIONAL_ARGS=()
while [ $# -gt 0 ]; do
    case "$1" in
        --env)
            ENV_FILE="${2:-}"
            shift 2
            ;;
        *)
            POSITIONAL_ARGS+=("$1")
            shift
            ;;
    esac
done
set -- "${POSITIONAL_ARGS[@]}"

if [ -n "$ENV_FILE" ]; then
    if [ ! -f "$ENV_FILE" ]; then
        echo "[ERROR] --env file not found: $ENV_FILE" >&2
        exit 2
    fi
    export CLOUD_DOG_ENV_FILES="$ENV_FILE"
fi

# Configuration
PID_DIR=".pids"
mkdir -p "$PID_DIR" logs 2>/dev/null || true

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

# Timing parameters - can be overridden via env
INITIAL_WAIT=${INITIAL_WAIT:-3}          # Wait after starting (seconds)
RETRY_INTERVAL=${RETRY_INTERVAL:-1}      # Time between checks (seconds)
MAX_WAIT=${MAX_WAIT:-15}                 # Max wait for start/stop (seconds)
SHUTDOWN_WAIT=${SHUTDOWN_WAIT:-10}       # Max wait for graceful shutdown (seconds)

# Server-specific timeouts (API and MCP need more time for initialization)
API_MAX_WAIT=30    # API server needs time for DB + initialization
MCP_MAX_WAIT=30    # MCP server also needs initialization
WEB_MAX_WAIT=15    # Web server starts quickly
A2A_MAX_WAIT=15    # A2A server starts quickly

# Logging
log_info() { echo -e "${GREEN}[INFO]${NC} $*"; }
log_warn() { echo -e "${YELLOW}[WARN]${NC} $*"; }
log_error() { echo -e "${RED}[ERROR]${NC} $*"; }
log_success() { echo -e "${GREEN}[SUCCESS]${NC} $*"; }

is_known_server() {
    case "$1" in
        api|web|mcp|a2a) return 0 ;;
        *) return 1 ;;
    esac
}

print_basic_help() {
    echo "═══════════════════════════════════════════════════════════════════"
    echo "  Expert Agent MCP Server - Help"
    echo "═══════════════════════════════════════════════════════════════════"
    echo ""
    echo "Usage: $0 [--env <env-file>] <command> [server]"
    echo ""
    echo "Commands:"
    echo "  start [server]      - Start server(s)"
    echo "  stop [server]       - Stop server(s) gracefully"
    echo "  restart [server]    - Restart server(s)"
    echo "  force-stop [server] - Force kill server(s)"
    echo "  status [server]     - Show status of one or all servers"
    echo "  status-all          - Show status of all servers"
    echo "  start-all           - Start all enabled servers"
    echo "  stop-all            - Stop all servers"
    echo "  force-stop-all      - Force stop all servers"
    echo "  help                - Show this help message"
    echo ""
    echo "Available Servers:"
    echo "  api"
    echo "  web"
    echo "  mcp"
    echo "  a2a"
    echo ""
    echo "Run 'status' or 'status-all' to inspect configured ports and runtime state."
    echo "═══════════════════════════════════════════════════════════════════"
}

# Read configuration from env and defaults.yaml
read_config() {
    local key=$1
    local default=$2
    local dotted_key
    dotted_key=$(printf '%s' "$key" | tr '[:upper:]' '[:lower:]' | sed 's/__/./g')
    python3 - "$dotted_key" "$default" <<'PY'
import sys
sys.path.insert(0, "src")
from config.loader import get_config

dotted_key = sys.argv[1]
default = sys.argv[2]
value = get_config(dotted_key, default=None)
if value is True:
    print("true")
elif value is False:
    print("false")
else:
    print(default if value is None or value == "" else value)
PY
}

# Get PID using port
get_port_pid() {
    local port=$1
    # Try multiple tools in order of preference
    if command -v netstat > /dev/null 2>&1; then
        netstat -tulpn 2>/dev/null | grep ":$port " | awk '{print $7}' | cut -d'/' -f1 | head -1
    elif command -v ss > /dev/null 2>&1; then
        ss -tulpn 2>/dev/null | grep ":$port " | awk '{print $7}' | sed 's/.*pid=\([0-9]*\).*/\1/' | head -1
    elif command -v lsof > /dev/null 2>&1; then
        lsof -ti :$port 2>/dev/null | head -1
    else
        # Fallback: check /proc/net/tcp (works in most Linux containers)
        local hex_port=$(printf '%04X' $port)
        awk -v port="$hex_port" '$2 ~ ":"port"$" {split($10,a,":"); print strtonum("0x"a[1])}' /proc/net/tcp 2>/dev/null | head -1
    fi
}

# Check if process is running
is_running() {
    local pid=$1
    [ -n "$pid" ] && ps -p "$pid" > /dev/null 2>&1
}

# Check if a TCP port is listening (PID mapping may be unavailable in some envs)
is_port_listening() {
    local port=$1
    if command -v ss > /dev/null 2>&1; then
        ss -ltn 2>/dev/null | awk '{print $4}' | grep -E "(^|:)${port}$" > /dev/null 2>&1
        return $?
    fi
    if command -v netstat > /dev/null 2>&1; then
        netstat -tln 2>/dev/null | awk '{print $4}' | grep -E "(^|:)${port}$" > /dev/null 2>&1
        return $?
    fi
    if command -v lsof > /dev/null 2>&1; then
        lsof -iTCP -sTCP:LISTEN -P -n 2>/dev/null | grep -E "[\.:]${port}[[:space:]]" > /dev/null 2>&1
        return $?
    fi
    return 1
}

# Server HTTP health check (more reliable than PID->port mapping in restricted envs)
check_server_http_health() {
    local server=$1
    local host=$2
    local port=$3
    local timeout_sec=${4:-2}
    local path=""
    case "$server" in
        api) path="/health" ;;
        web) path="/health" ;;
        a2a) path="/a2a/health" ;;
        mcp) path="/mcp/health" ;;
        *) return 1 ;;
    esac
    if ! command -v curl > /dev/null 2>&1; then
        return 1
    fi
    curl --noproxy '*' -sS -m "$timeout_sec" "http://${host}:${port}${path}" > /dev/null 2>&1
}

# Initialize server configuration from config files
init_server_config() {
    # API Server
    API_HOST=$(read_config "API_SERVER__HOST" "127.0.0.1")
    API_PORT=$(read_config "API_SERVER__PORT" "8083")
    API_ENABLED=$(read_config "API_SERVER__ENABLED" "true")
    
    WEB_HOST=$(read_config "WEB_SERVER__HOST" "127.0.0.1")
    # Web Server
    WEB_PORT=$(read_config "WEB_SERVER__PORT" "8080")
    WEB_ENABLED=$(read_config "WEB_SERVER__ENABLED" "true")
    
    MCP_HOST=$(read_config "MCP_SERVER__HOST" "127.0.0.1")
    # MCP Server
    MCP_PORT=$(read_config "MCP_SERVER__PORT" "8081")
    MCP_ENABLED=$(read_config "MCP_SERVER__ENABLED" "true")
    
    A2A_HOST=$(read_config "A2A_SERVER__HOST" "127.0.0.1")
    # A2A Server
    A2A_PORT=$(read_config "A2A_SERVER__PORT" "8082")
    A2A_ENABLED=$(read_config "A2A_SERVER__ENABLED" "true")
    
    # Server definitions: name:pid_file:port:script:log:enabled
    declare -g -A SERVERS
    SERVERS[api]="API Server:$PID_DIR/api_server.pid:$API_PORT:start_api_server.py:logs/api_server.log:$API_ENABLED"
    SERVERS[web]="Web Server:$PID_DIR/web_server.pid:$WEB_PORT:start_web_server.py:logs/web_server.log:$WEB_ENABLED"
    SERVERS[mcp]="MCP Server:$PID_DIR/mcp_server.pid:$MCP_PORT:start_mcp_server.py:logs/mcp_server.log:$MCP_ENABLED"
    SERVERS[a2a]="A2A Server:$PID_DIR/a2a_server.pid:$A2A_PORT:start_a2a_server.py:logs/a2a_server.log:$A2A_ENABLED"
}

# Get server config
get_config() {
    local server=$1
    echo "${SERVERS[$server]}"
}

# Parse config
parse_config() {
    IFS=':' read -r name pid_file port script log enabled <<< "$1"
}

# Status check for single server
status_server() {
    local server=$1
    local config=$(get_config "$server")
    [ -z "$config" ] && { log_error "Unknown server: $server"; return 1; }
    
    parse_config "$config"
    
    # Check if server is enabled in config
    if [ "$enabled" != "true" ]; then
        echo -e "  ${YELLOW}○${NC} $name: ${YELLOW}Disabled in config${NC}"
        return 0
    fi
    
    local pid=""
    local pid_valid=false
    local port_pid=""
    local port_listening=false
    
    [ -f "$pid_file" ] && pid=$(cat "$pid_file")
    is_running "$pid" && pid_valid=true
    port_pid=$(get_port_pid "$port")
    [ -n "$port_pid" ] && port_listening=true
    
    # MCP server can use either SSE (network port) or stdio (no port)
    # Check if it's actually listening on a port to determine transport
    if [ "$server" = "mcp" ]; then
        if [ "$pid_valid" = true ]; then
            if [ "$port_listening" = true ] && [ "$port_pid" = "$pid" ]; then
                # MCP is using SSE transport (network-based)
                echo -e "  ${GREEN}✓${NC} $name: ${GREEN}Running${NC} (PID: $pid, Port: $port) [SSE transport]"
                echo -e "    ${GREEN}✓${NC} Process running | ${GREEN}✓${NC} Port $port listening"
                return 0
            else
                # MCP is using stdio transport (pipe-based)
                echo -e "  ${GREEN}✓${NC} $name: ${GREEN}Running${NC} (PID: $pid) [stdio transport, no port]"
                echo -e "    ${GREEN}✓${NC} Process running"
                return 0
            fi
        else
            echo -e "  ${RED}✗${NC} $name: ${RED}Not Running${NC}"
            if [ -n "$pid" ]; then
                echo -e "    ${RED}✗${NC} Process PID:$pid DEAD"
            else
                echo -e "    ${RED}✗${NC} No PID file"
            fi
            return 1
        fi
    fi
    
    # Network-based servers: check port binding
    if [ "$pid_valid" = true ] && [ "$port_listening" = true ] && [ "$port_pid" = "$pid" ]; then
        echo -e "  ${GREEN}✓${NC} $name: ${GREEN}Running${NC} (PID: $pid, Port: $port)"
        echo -e "    ${GREEN}✓${NC} Process running | ${GREEN}✓${NC} Port $port listening"
        return 0
    elif [ "$pid_valid" = true ] && is_port_listening "$port" && { [ -z "$port_pid" ] || [ "$port_pid" = "-" ]; }; then
        echo -e "  ${GREEN}✓${NC} $name: ${GREEN}Running${NC} (PID: $pid, Port: $port)"
        echo -e "    ${GREEN}✓${NC} Process running | ${YELLOW}⚠${NC}  Port listening (PID mapping unavailable)"
        return 0
    else
        echo -e "  ${RED}✗${NC} $name: ${RED}Not Running${NC}"
        
        if [ -n "$pid" ]; then
            [ "$pid_valid" = true ] && echo -e "    ${GREEN}✓${NC} Process PID:$pid running" || echo -e "    ${RED}✗${NC} Process PID:$pid DEAD"
        else
            echo -e "    ${RED}✗${NC} No PID file"
        fi
        
        if [ "$port_listening" = true ]; then
            if [ "$port_pid" = "$pid" ]; then
                echo -e "    ${GREEN}✓${NC} Port $port listening"
            else
                echo -e "    ${YELLOW}⚠${NC}  Port $port occupied by PID:$port_pid (WRONG PROCESS)"
            fi
        else
            echo -e "    ${RED}✗${NC} Port $port not listening"
        fi
        return 1
    fi
}

# Start single server
start_server() {
    local server=$1
    local config=$(get_config "$server")
    [ -z "$config" ] && { log_error "Unknown server: $server"; return 1; }
    
    parse_config "$config"
    
    # Check if server is enabled
    if [ "$enabled" != "true" ]; then
        log_warn "$name is disabled in configuration - skipping"
        return 0
    fi
    
    log_info "Starting $name (port: $port)..."
    
    # Check current status
    local pid=""
    local pid_valid=false
    [ -f "$pid_file" ] && pid=$(cat "$pid_file")
    is_running "$pid" && pid_valid=true
    
    local port_pid=$(get_port_pid "$port")
    
    # Handle states
    if [ "$pid_valid" = true ] && { [ "$port_pid" = "$pid" ] || { is_port_listening "$port" && { [ -z "$port_pid" ] || [ "$port_pid" = "-" ]; }; }; }; then
        log_warn "$name is already running (PID: $pid, Port: $port)"
        log_warn "Use 'stop $server' first, or 'restart $server'"
        return 1
    fi
    
    if [ "$pid_valid" = false ] && [ -f "$pid_file" ]; then
        log_warn "Found dead PID file (PID: $pid) - cleaning up"
        rm -f "$pid_file"
    fi
    
    if [ -n "$port_pid" ] && [ "$port_pid" != "$pid" ]; then
        log_error "Port $port is occupied by PID: $port_pid"
        log_error "Use 'force-stop $server' to kill it"
        return 1
    fi
    
    # Prefer the project venv only when it can actually import the required
    # platform/runtime modules. Some authorised baseline worktrees keep a stale
    # venv around; in that case fall back to the active python3 instead of
    # booting a partially provisioned interpreter.
    local python_bin="$SCRIPT_DIR/venv/bin/python"
    if [ -x "$python_bin" ]; then
        if ! "$python_bin" - <<'PY' >/dev/null 2>&1
import importlib.util
required = [
    "cloud_dog_config",
    "cloud_dog_logging",
    "cloud_dog_api_kit",
    "cloud_dog_storage",
]
missing = [name for name in required if importlib.util.find_spec(name) is None]
raise SystemExit(0 if not missing else 1)
PY
        then
            python_bin="python3"
        fi
    else
        python_bin="python3"
    fi

    # Detach into a separate session so test/plugin process-group cleanup does not
    # send SIGTERM into the managed local server stack mid-run.
    #
    # IMPORTANT: do not wrap `setsid` inside `nohup`. In this repo that launch
    # pattern can die immediately with a shell-level "Killed" before the server
    # emits any startup logs, even though the same interpreter/script starts
    # cleanly in the foreground. Running `setsid` directly matches the stable
    # local-server pattern used elsewhere in the platform.
    if command -v setsid >/dev/null 2>&1; then
        setsid "$python_bin" "$script" > "$log" 2>&1 < /dev/null &
    else
        nohup "$python_bin" "$script" > "$log" 2>&1 < /dev/null &
    fi
    local new_pid=$!
    disown "$new_pid" 2>/dev/null || true
    echo "$new_pid" > "$pid_file"
    
    log_info "Waiting ${INITIAL_WAIT}s for startup..."
    sleep "$INITIAL_WAIT"
    
    # Use server-specific timeout or default
    local server_max_wait=$MAX_WAIT
    case "$server" in
        api) server_max_wait=$API_MAX_WAIT ;;
        mcp) server_max_wait=$MCP_MAX_WAIT ;;
        web) server_max_wait=$WEB_MAX_WAIT ;;
        a2a) server_max_wait=$A2A_MAX_WAIT ;;
    esac
    
    # Validate - check if MCP is using SSE (port) or stdio (no port)
    local elapsed=0
    
    # Resolve host for health checks
    local host="127.0.0.1"
    case "$server" in
        api) host="$API_HOST" ;;
        web) host="$WEB_HOST" ;;
        mcp) host="$MCP_HOST" ;;
        a2a) host="$A2A_HOST" ;;
    esac

    # MCP can use either SSE or stdio - check which one is configured
    if [ "$server" = "mcp" ]; then
        # Wait and check if it binds to a port (SSE) or not (stdio)
        while [ $elapsed -lt $server_max_wait ]; do
            if is_running "$new_pid"; then
                if check_server_http_health "$server" "$host" "$port" 2; then
                    # MCP is using SSE transport (has port)
                    log_success "$name started (PID: $new_pid, Port: $port) [SSE transport]"
                    return 0
                elif [ $elapsed -ge 5 ]; then
                    # After 5s, if no port, assume stdio transport
                    log_success "$name started (PID: $new_pid) [stdio transport, no port]"
                    return 0
                fi
            else
                log_error "$name process died - check $log"
                rm -f "$pid_file"
                return 1
            fi
            sleep "$RETRY_INTERVAL"
            elapsed=$((elapsed + RETRY_INTERVAL))
        done
        log_error "$name failed to stabilize within ${server_max_wait}s"
        kill -9 "$new_pid" 2>/dev/null || true
        rm -f "$pid_file"
        return 1
    fi
    
    # Network-based servers: validate via HTTP health endpoint first; fallback to port checks
    while [ $elapsed -lt $server_max_wait ]; do
        if is_running "$new_pid"; then
            if check_server_http_health "$server" "$host" "$port" 2; then
                log_success "$name started (PID: $new_pid, Port: $port)"
                return 0
            fi

            local actual_port_pid=$(get_port_pid "$port")
            if [ "$actual_port_pid" = "$new_pid" ]; then
                log_success "$name started (PID: $new_pid, Port: $port)"
                return 0
            elif is_port_listening "$port" && { [ -z "$actual_port_pid" ] || [ "$actual_port_pid" = "-" ]; }; then
                log_success "$name started (PID: $new_pid, Port: $port) [port listening, PID mapping unavailable]"
                return 0
            fi
        else
            log_error "$name process died - check $log"
            rm -f "$pid_file"
            return 1
        fi
        
        sleep "$RETRY_INTERVAL"
        elapsed=$((elapsed + RETRY_INTERVAL))
    done
    
    log_error "$name failed to bind to port $port within ${server_max_wait}s"
    kill -9 "$new_pid" 2>/dev/null || true
    rm -f "$pid_file"
    return 1
}

# Stop single server
stop_server() {
    local server=$1
    local config=$(get_config "$server")
    [ -z "$config" ] && { log_error "Unknown server: $server"; return 1; }
    
    parse_config "$config"
    log_info "Stopping $name..."
    
    local pid=""
    local pid_valid=false
    [ -f "$pid_file" ] && pid=$(cat "$pid_file")
    is_running "$pid" && pid_valid=true
    
    local port_pid=$(get_port_pid "$port")
    
    # Handle states
    if [ "$pid_valid" = false ] && [ -z "$port_pid" ]; then
        if [ -f "$pid_file" ]; then
            log_warn "$name not running (dead PID: $pid) - cleaning up"
            rm -f "$pid_file"
        else
            log_warn "$name is not running"
        fi
        return 0
    fi
    
    if [ "$pid_valid" = false ] && [ -n "$port_pid" ]; then
        log_error "PID invalid but port $port occupied by PID: $port_pid"
        log_error "Use 'force-stop $server'"
        return 1
    fi
    
    # Graceful stop
    log_info "Sending SIGTERM to $name (PID: $pid)..."
    kill -TERM "$pid" 2>/dev/null || true
    
    local elapsed=0
    while [ $elapsed -lt $SHUTDOWN_WAIT ]; do
        if ! is_running "$pid"; then
            log_success "$name stopped gracefully"
            rm -f "$pid_file"
            return 0
        fi
        sleep "$RETRY_INTERVAL"
        elapsed=$((elapsed + RETRY_INTERVAL))
    done
    
    # Force kill
    log_warn "$name did not stop gracefully, forcing..."
    kill -9 "$pid" 2>/dev/null || true
    sleep 1
    rm -f "$pid_file"
    log_success "$name stopped (forced)"
    return 0
}

# Force stop single server
force_stop_server() {
    local server=$1
    local config=$(get_config "$server")
    [ -z "$config" ] && { log_error "Unknown server: $server"; return 1; }
    
    parse_config "$config"
    log_info "Force-stopping $name..."
    
    local pid=""
    [ -f "$pid_file" ] && pid=$(cat "$pid_file")
    local port_pid=$(get_port_pid "$port")
    
    # Kill PID file process
    if [ -n "$pid" ] && is_running "$pid"; then
        log_info "Killing PID: $pid..."
        kill -9 "$pid" 2>/dev/null || true
    fi
    
    # Kill port process
    if [ -n "$port_pid" ]; then
        log_info "Killing process on port $port (PID: $port_pid)..."
        kill -9 "$port_pid" 2>/dev/null || true
    fi
    
    rm -f "$pid_file"
    sleep "$RETRY_INTERVAL"
    
    if [ -z "$(get_port_pid "$port")" ]; then
        log_success "$name force-stopped"
        return 0
    else
        log_error "Port $port still occupied"
        return 1
    fi
}

# Preserve explicit env-file context across internal recursive invocations.
# Without this, aliases like `start-all` fall back to build/runtime env and can
# launch servers with incorrect configuration.
FORWARD_ENV_ARGS=()
if [ -n "$ENV_FILE" ]; then
    FORWARD_ENV_ARGS=(--env "$ENV_FILE")
fi

COMMAND="${1:-}"
TARGET_SERVER="${2:-}"

# Fast-path non-runtime commands before config resolution so basic script
# contracts do not block on slow external config backends.
case "$COMMAND" in
    help)
        print_basic_help
        exit 0
        ;;
    start|stop|restart|force-stop|status)
        if [ -n "$TARGET_SERVER" ] && ! is_known_server "$TARGET_SERVER"; then
            log_error "Unknown server: $TARGET_SERVER"
            exit 1
        fi
        ;;
    start-all|stop-all|force-stop-all|status-all|"")
        ;;
    *)
        echo "Unknown command: $COMMAND"
        echo ""
        echo "Run './server_control.sh help' for available commands"
        exit 1
        ;;
esac

# Initialize configuration
init_server_config

# Main commands
case "$COMMAND" in
    start)
        if [ -n "$2" ]; then
            start_server "$2"
        else
            echo "Starting all enabled servers..."
            for s in api mcp a2a web; do start_server "$s" || true; done
        fi
        ;;
    stop)
        if [ -n "$2" ]; then
            stop_server "$2"
        else
            echo "Stopping all servers..."
            for s in web a2a mcp api; do stop_server "$s" || true; done
        fi
        ;;
    restart)
        if [ -n "$2" ]; then
            stop_server "$2" && sleep 2 && start_server "$2"
        else
            "$0" "${FORWARD_ENV_ARGS[@]}" stop && sleep 2 && "$0" "${FORWARD_ENV_ARGS[@]}" start
        fi
        ;;
    force-stop)
        if [ -n "$2" ]; then
            force_stop_server "$2"
        else
            echo "Force-stopping all servers..."
            for s in web a2a mcp api; do force_stop_server "$s" || true; done
        fi
        ;;
    status)
        echo "═══════════════════════════════════════════════════════════════════"
        echo "  Expert Agent MCP Server - Status"
        echo "  (Ports from configuration: API=$API_PORT, Web=$WEB_PORT, MCP=$MCP_PORT, A2A=$A2A_PORT)"
        echo "═══════════════════════════════════════════════════════════════════"
        echo ""
        if [ -n "$2" ]; then
            status_server "$2"
        else
            for s in api web mcp a2a; do status_server "$s"; echo ""; done
        fi
        echo "═══════════════════════════════════════════════════════════════════"
        ;;
    status-all)
        echo "═══════════════════════════════════════════════════════════════════"
        echo "  Expert Agent MCP Server - Status (All Servers)"
        echo "  (Ports from configuration: API=$API_PORT, Web=$WEB_PORT, MCP=$MCP_PORT, A2A=$A2A_PORT)"
        echo "═══════════════════════════════════════════════════════════════════"
        echo ""
        for s in api web mcp a2a; do status_server "$s"; echo ""; done
        echo "═══════════════════════════════════════════════════════════════════"
        ;;
    start-all) "$SELF_PATH" "${FORWARD_ENV_ARGS[@]}" start ;;
    stop-all) "$SELF_PATH" "${FORWARD_ENV_ARGS[@]}" stop ;;
    force-stop-all) "$SELF_PATH" "${FORWARD_ENV_ARGS[@]}" force-stop ;;
    help)
        print_basic_help
        ;;
    "")
        # No command - show status of all servers
        echo "═══════════════════════════════════════════════════════════════════"
        echo "  Expert Agent MCP Server - Status"
        echo "  (Ports from configuration: API=$API_PORT, Web=$WEB_PORT, MCP=$MCP_PORT, A2A=$A2A_PORT)"
        echo "═══════════════════════════════════════════════════════════════════"
        echo ""
        for s in api web mcp a2a; do status_server "$s"; echo ""; done
        echo "═══════════════════════════════════════════════════════════════════"
        echo ""
        echo "Run './server_control.sh help' for available commands"
        ;;
esac
