---
name: "github-workflow"
description: "Branch strategy, PR flow, and environment promotion"
metadata:
  author: agent-webapp-template
  version: 1.0.0
---

Branch strategy, PR flow, and environment promotion for this project.

## Branch model

```
main          ← production (auto-deploys to Render prod, uses Supabase prod DB)
  └── dev     ← staging (auto-deploys to Render staging, uses Supabase staging DB)
        └── feature/<name>   ← all active work
```

- **`main`** is always deployable. Every commit here goes live to production.
- **`dev`** is the integration branch. Feature branches merge here first and get validated in the staging environment before anything reaches `main`.
- **`feature/<name>`** branches are short-lived. Cut from `dev`, merged back to `dev` via PR, then deleted.

Never commit directly to `main` or `dev`.

---

## Day-to-day development cycle

### 1. Cut a feature branch from `dev`
```bash
git checkout dev
git pull origin dev
git checkout -b feature/<name>
```

### 2. Do the work
Make commits on `feature/<name>`. Keep commits small and focused — one concern per commit.

### 3. PR: feature → dev
Push the branch and open a PR targeting `dev`:

```bash
git push -u origin feature/<name>
gh pr create --base dev --title "<title>" --body "<description>"
```

- The staging Render services auto-deploy when `dev` is updated, so the change is live in staging after merge.
- Verify the feature works against the staging environment and staging database before moving on.

### 4. PR: dev → main (promotion to production)
When staging looks good, open a PR from `dev` to `main`:

```bash
gh pr create --base main --head dev --title "Promote dev → main" --body "<summary of changes>"
```

- Review the diff carefully — this is what goes to production.
- Merge only when staging is stable and all intended features for this release are included.
- Render auto-deploys the prod services on merge to `main`.

---

## Environment variables per branch

Each environment has its own Render services and its own Supabase project. The only difference between staging and prod is the values of the environment variables — the code is identical.

| Variable | Staging value | Production value |
|---|---|---|
| `APP_ENV` | `staging` | `production` |
| `DATABASE_URL` | Supabase **staging** project pooler URL | Supabase **prod** project pooler URL |
| `ALLOWED_ORIGINS` | Render staging frontend URL | Render prod frontend URL |
| `SECRET_KEY` | staging secret | production secret (different value) |
| All others | staging equivalents | production equivalents |

Set these in the Render dashboard for each service — never in code or committed files.

---

## Setting up Render auto-deploy per branch

In each Render service → **Settings → Deploy**:

- **Production services** (backend + frontend): connect to the `main` branch.
- **Staging services** (backend + frontend): connect to the `dev` branch.

Render will redeploy automatically on every push to the connected branch.

---

## Hotfixes

For urgent production fixes that can't wait for the normal `dev → main` cycle:

1. Cut `hotfix/<name>` from `main`.
2. Fix and open a PR to `main`.
3. After merging, immediately merge `main` back into `dev` to keep them in sync:

```bash
git checkout dev
git pull origin dev
git merge origin/main
git push origin dev
```

---

## Rules of thumb

- A PR to `dev` needs at least a passing local test run before merge.
- A PR to `main` needs the feature validated in staging — don't promote untested changes.
- Delete feature branches after merge to keep the branch list clean.
- The staging database mirrors the production schema but contains only test data — never copy production data to staging.
