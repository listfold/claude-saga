#!/bin/bash

# Claude Conversation Logger - Zero Dependencies
# Uses only bash built-ins to parse JSON and log conversations

# Read input from stdin
INPUT=""
while IFS= read -r line; do
    INPUT="${INPUT}${line}"
done

# Simple JSON parser using bash pattern matching
extract_json_value() {
    local json="$1"
    local key="$2"
    local value=""
    
    # Find the key and extract its value
    if [[ "$json" =~ \"$key\"[[:space:]]*:[[:space:]]*\"([^\"]+)\" ]]; then
        value="${BASH_REMATCH[1]}"
    elif [[ "$json" =~ \"$key\"[[:space:]]*:[[:space:]]*(true|false|null|[0-9]+) ]]; then
        value="${BASH_REMATCH[1]}"
    fi
    
    echo "$value"
}

# Extract fields from input
SESSION_ID=$(extract_json_value "$INPUT" "session_id")
TRANSCRIPT_PATH=$(extract_json_value "$INPUT" "transcript_path")
STOP_HOOK_ACTIVE=$(extract_json_value "$INPUT" "stop_hook_active")

# Exit if stop hook is already active
if [ "$STOP_HOOK_ACTIVE" = "true" ]; then
    exit 0
fi

# Expand tilde in path
TRANSCRIPT_PATH="${TRANSCRIPT_PATH/#\~/$HOME}"

# Create logs directory
LOGS_DIR="$(pwd)/.claude-logs"
mkdir -p "$LOGS_DIR"

# Check if transcript exists
if [ ! -f "$TRANSCRIPT_PATH" ]; then
    exit 0
fi

# Save the raw transcript
cp "$TRANSCRIPT_PATH" "$LOGS_DIR/latest.jsonl"

# Create a simple text log
{
    echo "CLAUDE CONVERSATION LOG"
    echo "======================"
    echo "Session: $SESSION_ID"
    echo "Updated: $(date)"
    echo ""
    
    # Read transcript line by line (JSONL format)
    while IFS= read -r line; do
        if [ -n "$line" ]; then
            # Extract role and content using bash string manipulation
            if [[ "$line" =~ \"role\"[[:space:]]*:[[:space:]]*\"([^\"]+)\" ]]; then
                ROLE="${BASH_REMATCH[1]}"
                
                # Extract content (handling escaped quotes)
                if [[ "$line" =~ \"content\"[[:space:]]*:[[:space:]]*\"(.*)\"[[:space:]]*\} ]]; then
                    CONTENT="${BASH_REMATCH[1]}"
                    
                    # Basic unescape
                    CONTENT="${CONTENT//\\n/$'\n'}"
                    CONTENT="${CONTENT//\\\"/\"}"
                    CONTENT="${CONTENT//\\\\/\\}"
                    
                    echo "[$ROLE]"
                    echo "$CONTENT"
                    echo ""
                    echo "---"
                    echo ""
                fi
            fi
        fi
    done < "$TRANSCRIPT_PATH"
} > "$LOGS_DIR/latest.txt"

# Keep a timestamped backup every 10 interactions
LINE_COUNT=$(wc -l < "$TRANSCRIPT_PATH" | tr -d ' ')
if [ $((LINE_COUNT % 20)) -eq 0 ] && [ "$LINE_COUNT" -gt 0 ]; then
    TIMESTAMP=$(date +"%Y%m%d_%H%M%S")
    cp "$LOGS_DIR/latest.jsonl" "$LOGS_DIR/backup_${TIMESTAMP}.jsonl"
    cp "$LOGS_DIR/latest.txt" "$LOGS_DIR/backup_${TIMESTAMP}.txt"
fi