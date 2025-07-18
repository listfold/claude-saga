#!/bin/bash
# hook-utils.sh - Common utilities for Claude Code hooks

# ============================================================================
# LOGGING
# ============================================================================
log_debug() {
    [[ "${DEBUG:-0}" == "1" ]] && echo "[DEBUG] $*" >&2
}

log_info() {
    echo "[INFO] $*" >&2
}

log_error() {
    echo "[ERROR] $*" >&2
}

# ============================================================================
# UTILITIES
# ============================================================================
command_exists() {
    command -v "$1" >/dev/null 2>&1
}

# ============================================================================
# HOOK INPUT PARSING
# ============================================================================
# Parse hook JSON input and set SESSION_ID and TRANSCRIPT_PATH variables
parse_hook_input() {
    if ! command_exists jq; then
        log_error "jq is required for JSON parsing but not found"
        return 1
    fi
    
    local json_input=$(cat)
    
    SESSION_ID=$(echo "$json_input" | jq -r '.session_id // empty')
    TRANSCRIPT_PATH=$(echo "$json_input" | jq -r '.transcript_path // empty')
    
    if [[ -z "$SESSION_ID" ]]; then
        log_error "No session_id found in JSON input"
        return 1
    fi
    
    if [[ -z "$TRANSCRIPT_PATH" ]]; then
        log_error "No transcript_path found in JSON input"
        return 1
    fi
    
    log_debug "Session ID: $SESSION_ID"
    log_debug "Transcript Path: $TRANSCRIPT_PATH"
    
    # Export so they're available to calling script
    export SESSION_ID
    export TRANSCRIPT_PATH
    
    return 0
}

# ============================================================================
# JSON OUTPUT HELPERS
# ============================================================================
output_json_response() {
    local action="$1"
    local message="$2"
    shift 2
    
    local json='{'
    
    case "$action" in
        "continue")
            json+='"action":"continue"'
            ;;
        "block")
            json+='"action":"block"'
            ;;
        "error")
            json+='"action":"error"'
            ;;
    esac
    
    if [[ -n "$message" ]]; then
        json+=",\"message\":\"$(echo -n "$message" | sed 's/"/\\"/g')\""
    fi
    
    for field in "$@"; do
        local key="${field%%:*}"
        local value="${field#*:}"
        json+=",\"$key\":\"$(echo -n "$value" | sed 's/"/\\"/g')\""
    done
    
    json+='}'
    
    echo "$json"
}
