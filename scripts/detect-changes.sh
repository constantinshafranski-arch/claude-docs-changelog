#!/bin/bash
set -euo pipefail

# Usage: detect-changes.sh <docs-mirror-dir> [lookback]
# Detects changed .md files in the docs mirror and builds CONTEXT.md

DOCS_DIR="$1"
LOOKBACK="${2:-24 hours ago}"
REPO_ROOT=$(pwd)

cd "$DOCS_DIR"

# Find changed .md files (exclude manifests/indexes)
CHANGED=$(git log --since="$LOOKBACK" --diff-filter=AMR \
  --name-only --pretty="" -- 'docs/*.md' \
  | grep -v 'docs_manifest\|search_index\|changelog\.md' | sort -u || true)

if [[ -z "$CHANGED" ]]; then
  echo "has_changes=false" >> "$GITHUB_OUTPUT"
  echo "No documentation changes found in the last $LOOKBACK"
  exit 0
fi

echo "has_changes=true" >> "$GITHUB_OUTPUT"
FILE_COUNT=$(echo "$CHANGED" | wc -l | tr -d ' ')
echo "file_count=$FILE_COUNT" >> "$GITHUB_OUTPUT"
echo "Found $FILE_COUNT changed doc files"

# Build CONTEXT.md with categorized changes + diffs
CONTEXT_FILE="$REPO_ROOT/CONTEXT.md"
MIRROR_DIR=$(pwd)

cat > "$CONTEXT_FILE" << 'HEADER'
# Documentation Changes Detected
HEADER

echo "Date: $(date -u +%Y-%m-%d)" >> "$CONTEXT_FILE"
echo "Files changed: $FILE_COUNT" >> "$CONTEXT_FILE"
echo "" >> "$CONTEXT_FILE"

# Category mapping function
categorize() {
  case "$1" in
    docs/claude-code__*)                          echo "Claude Code CLI" ;;
    docs/docs__en__agent-sdk__*)                  echo "Agent SDK" ;;
    docs/docs__en__api__*)                        echo "API Reference" ;;
    docs/docs__en__build-*)                       echo "Platform" ;;
    docs/docs__en__about-claude__*)               echo "About Claude" ;;
    docs/docs__en__agents-and-tools__*)           echo "Agents & Tools" ;;
    docs/docs__en__test-and-evaluate__*)          echo "Testing & Evaluation" ;;
    docs/docs__en__release-notes__*)              echo "Release Notes" ;;
    docs/docs__en__resources__prompt-library__*)  echo "Prompt Library" ;;
    docs/docs__en__resources__*)                  echo "Resources" ;;
    docs/docs__en__get-started.md|docs/docs__en__intro.md) echo "Getting Started" ;;
    *)                                            echo "Other" ;;
  esac
}

CURRENT_CAT=""
while IFS= read -r file; do
  CAT=$(categorize "$file")
  if [[ "$CAT" != "$CURRENT_CAT" ]]; then
    echo "" >> "$CONTEXT_FILE"
    echo "## Category: $CAT" >> "$CONTEXT_FILE"
    CURRENT_CAT="$CAT"
  fi

  # Check if new or modified
  IS_NEW=$(git log --since="$LOOKBACK" --diff-filter=A \
    --name-only --pretty="" -- "$file" | head -1)

  if [[ -n "$IS_NEW" ]]; then
    echo "### $file [NEW]" >> "$CONTEXT_FILE"
  else
    echo "### $file [UPDATED]" >> "$CONTEXT_FILE"
  fi

  # Add git log summary
  echo '```' >> "$CONTEXT_FILE"
  git log --since="$LOOKBACK" --oneline -- "$file" >> "$CONTEXT_FILE"
  echo '```' >> "$CONTEXT_FILE"

  # Add diff excerpt (truncated to 200 lines per file)
  echo "Diff:" >> "$CONTEXT_FILE"
  echo '```diff' >> "$CONTEXT_FILE"
  git log --since="$LOOKBACK" -p -- "$file" \
    | head -200 >> "$CONTEXT_FILE" 2>/dev/null || true
  echo '```' >> "$CONTEXT_FILE"
  echo "" >> "$CONTEXT_FILE"

done <<< "$CHANGED"

echo "CONTEXT.md built at $CONTEXT_FILE"
