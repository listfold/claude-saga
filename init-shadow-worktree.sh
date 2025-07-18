#!/bin/bash
# ai-shadow-init.sh - Initialize git shadow worktree for AI undo tracking

set -euo pipefail

# ============================================================================
# LOAD UTILITIES
# ============================================================================
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$SCRIPT_DIR/hook-utils.sh" || {
    echo "[ERROR] Failed to load hook-utils.sh" >&2
    exit 1
}

# ============================================================================
# CONFIGURATION
# ============================================================================
DEBUG="${DEBUG:-0}"

# ============================================================================
# ENVIRONMENT CHECKS
# ============================================================================
# Get git root (will fail if not in a git repo)
MAIN_REPO_ROOT=$(git rev-parse --show-toplevel 2>/dev/null) || {
    log_error "Not a git repo, init git to use this tool"
    exit 1
}
cd "$MAIN_REPO_ROOT"

# ============================================================================
# HOOK INPUT PARSING
# ============================================================================
# Parse input and get SESSION_ID and TRANSCRIPT_PATH
parse_hook_input || exit 1

# ============================================================================
# SHADOW WORKTREE INITIALIZATION
# ============================================================================

# Set up paths in .claude directory
SHADOW_DIR="$MAIN_REPO_ROOT/.claude/efficient-undo/session-$SESSION_ID-worktree"
INITIAL_STATE_FILE="$MAIN_REPO_ROOT/.claude/efficient-undo/session-$SESSION_ID-initial.patch"

# Check if shadow worktree already exists
if git worktree list | grep -q "$SHADOW_DIR"; then
    log_info "Shadow worktree already exists for session $SESSION_ID"
    output_json_response "continue" "Shadow worktree already exists" \
        "session_id:$SESSION_ID" \
        "shadow_dir:$SHADOW_DIR"
    exit 0
fi

log_info "Initializing shadow worktree for session $SESSION_ID"

# Capture current state including uncommitted changes
git add -N . 2>/dev/null || true
git diff HEAD > "$INITIAL_STATE_FILE"

# Create detached worktree at current HEAD
git worktree add -d "$SHADOW_DIR" HEAD

# Apply initial state to shadow
cd "$SHADOW_DIR"
git apply "$INITIAL_STATE_FILE" 2>/dev/null || true
git add -A
git commit --allow-empty -m "Initial state: session $SESSION_ID" || true
log_info "Shadow worktree initialized"

cd "$MAIN_REPO_ROOT"

# Output success response
output_json_response "continue" "Shadow worktree initialized" \
    "session_id:$SESSION_ID" \
    "shadow_dir:$SHADOW_DIR"
