#!/usr/bin/env bash
# Sync this repo's skills/ with the upstream template.
#
# Pulls new and updated skills from the template repo into ./skills and stages
# them for review. Repo-local skills that don't exist upstream are left alone.
#
# Override the source with env vars:
#   TEMPLATE_REMOTE_URL  (default: the agent-webapp-template GitHub repo)
#   TEMPLATE_REF         (default: main)
set -euo pipefail

TEMPLATE_URL="${TEMPLATE_REMOTE_URL:-https://github.com/tascoma/agent-webapp-template.git}"
TEMPLATE_REF="${TEMPLATE_REF:-main}"

# Must be run inside a git work tree.
git rev-parse --is-inside-work-tree >/dev/null 2>&1 || {
  echo "error: not inside a git repository" >&2
  exit 1
}
cd "$(git rev-parse --show-toplevel)"

# Ensure the 'template' remote points at the upstream template.
if git remote get-url template >/dev/null 2>&1; then
  git remote set-url template "$TEMPLATE_URL"
else
  git remote add template "$TEMPLATE_URL"
fi

echo "Fetching skills from $TEMPLATE_URL ($TEMPLATE_REF)..."
git fetch --quiet template "$TEMPLATE_REF"

# Bring upstream skills/ into the working tree + index. This adds/updates the
# paths present upstream; it does not delete repo-local skills.
git checkout "template/$TEMPLATE_REF" -- skills

echo
if git diff --staged --quiet -- skills; then
  echo "Already in sync — no skill changes from upstream."
else
  echo "Upstream skills synced into ./skills (staged). Review, then commit:"
  git status --short -- skills
  echo
  echo "  git diff --staged skills                  # inspect the changes"
  echo "  git commit -m 'Sync skills from template' # keep them"
  echo "  git restore --staged --worktree skills    # abort and discard"
fi
