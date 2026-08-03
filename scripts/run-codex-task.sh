#!/usr/bin/env bash

set -Eeuo pipefail

usage() {
  echo "Usage: $0 .codex/tasks/<task>.md" >&2
  exit 1
}

TASK_FILE="${1:-}"

[[ -n "$TASK_FILE" ]] || usage
[[ -f "$TASK_FILE" ]] || {
  echo "Task file does not exist: $TASK_FILE" >&2
  exit 1
}

REPO_ROOT="$(git rev-parse --show-toplevel 2>/dev/null)" || {
  echo "This command must be run inside a Git repository." >&2
  exit 1
}

cd "$REPO_ROOT"

CURRENT_BRANCH="$(git branch --show-current)"

if [[ -z "$CURRENT_BRANCH" ]]; then
  echo "Codex will not run from a detached HEAD." >&2
  exit 1
fi

TASK_NAME="$(basename "$TASK_FILE" .md)"
TIMESTAMP="$(date +"%Y%m%d-%H%M%S")"
RESULT_DIR=".codex/results/$TASK_NAME-$TIMESTAMP"
RESULT_FILE="$RESULT_DIR/result.md"
DIFF_FILE="$RESULT_DIR/changes.diff"
STATUS_FILE="$RESULT_DIR/git-status.txt"
STAT_FILE="$RESULT_DIR/diff-stat.txt"

mkdir -p "$RESULT_DIR"

EXPECTED_BRANCH="$(
  awk '
    BEGIN { found = 0 }
    /^Expected branch:[[:space:]]*/ {
      sub(/^Expected branch:[[:space:]]*/, "")
      gsub(/^[[:space:]]+|[[:space:]]+$/, "")
      print
      found = 1
      exit
    }
    END {
      if (!found) print ""
    }
  ' "$TASK_FILE"
)"

if [[ -n "$EXPECTED_BRANCH" && "$EXPECTED_BRANCH" != "$CURRENT_BRANCH" ]]; then
  echo "Branch mismatch." >&2
  echo "Task expects: $EXPECTED_BRANCH" >&2
  echo "Current branch: $CURRENT_BRANCH" >&2
  echo "Codex has not been started." >&2
  exit 1
fi

if [[ -n "$(git status --porcelain)" ]]; then
  echo "Warning: this worktree already contains uncommitted changes."
  git status --short
  echo
  read -r -p "Continue with this existing state? [y/N] " RESPONSE

  case "$RESPONSE" in
    y|Y|yes|YES)
      ;;
    *)
      echo "Cancelled."
      exit 1
      ;;
  esac
fi

{
  cat <<EOF
You are implementing a bounded coding task in a Git worktree.

Repository root: $REPO_ROOT
Current branch: $CURRENT_BRANCH
Task specification: $TASK_FILE

Operating requirements:

1. Read the task specification below in full.
2. Read the files named in its "Read first" section.
3. Treat the supplied architecture and context as the discovery baseline.
4. Begin with the explicitly named implementation areas and canonical examples.
5. Do not repeat broad repository discovery.
6. Use targeted searches only for relevant symbols, imports, interfaces and direct call sites.
7. Verify the files you modify, their direct dependencies, dependency wiring and affected tests.
8. Do not modify excluded areas.
9. Reuse established project libraries and patterns where suitable.
10. Run the verification commands listed in the task.
11. Do not commit, push or open a pull request.

Your final report must include:

- Summary of changes
- Files changed
- Tests and checks executed
- Test results
- Any specification/repository mismatch
- Any remaining risks or unresolved issues

Here is the task specification:

EOF

  cat "$TASK_FILE"
} | codex exec - \
      --sandbox workspace-write \
      --output-last-message "$RESULT_FILE"

git status --short > "$STATUS_FILE"
git diff --stat > "$STAT_FILE"
git diff > "$DIFF_FILE"

echo
echo "Codex run complete."
echo "Result:     $RESULT_FILE"
echo "Git status: $STATUS_FILE"
echo "Diff stat:  $STAT_FILE"
echo "Diff:       $DIFF_FILE"