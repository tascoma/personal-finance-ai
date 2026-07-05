---
name: "sync-skills"
description: "Sync this repo's skills with the upstream template, pulling in new and updated skills"
metadata:
  author: agent-webapp-template
  version: 1.0.0
---

Keep a repo created from this template up to date with the template's skill library. Pulls new and updated skills from upstream into `skills/` and stages them for review. Repo-local skills you've added yourself are never touched.

## How it works
The template is added as a git remote named `template`. Running the sync fetches it and does `git checkout template/<ref> -- skills`, which writes upstream skill files into your working tree and stages them. Because it operates on a pathspec, it **adds and updates** the skills that exist upstream and leaves your own custom skills in place — it never deletes them.

## Steps

### 1. Run the sync
From anywhere in the repo:

```bash
bash skills/sync-skills/scripts/sync-skills.sh
```

The script adds (or updates) the `template` remote, fetches it, and stages the upstream `skills/`. To sync from a fork or a different branch, override the defaults:

```bash
TEMPLATE_REMOTE_URL=https://github.com/<you>/<fork>.git TEMPLATE_REF=dev \
  bash skills/sync-skills/scripts/sync-skills.sh
```

### 2. Review before committing
The script stages changes but does not commit. Inspect what upstream changed:

```bash
git diff --staged skills
```

Compare `metadata.version` in each skill's frontmatter to see what was bumped upstream.

### 3. Keep or abort
```bash
git commit -m "Sync skills from template"     # keep the updates
git restore --staged --worktree skills        # discard and revert
```

## Caveat
This **overwrites local edits to template-managed skills** (any skill that also exists upstream) with the upstream version. Always review `git diff --staged skills` before committing. If you've customized a template skill and want to keep your changes, either copy them under a new skill name first, or resolve the diff by hand before committing.

## Verification
Run the script in a clean working tree:

```bash
bash skills/sync-skills/scripts/sync-skills.sh
```

It adds the `template` remote, fetches, and exits 0. When already in sync it prints "Already in sync — no skill changes from upstream." Confirm none of your repo-local skills were removed (`git status` shows only additions/updates, never deletions of your own skills).
