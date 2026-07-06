---
name: "setup-ci"
description: "Add GitHub Actions for CI and auto-deploy to Render"
metadata:
  author: agent-webapp-template
  version: 1.0.0
---

Set up GitHub Actions to lint and test on every push, and deploy to Render automatically on merge to `dev` or `main`.

## Steps

### 1. Create the workflows directory
```bash
mkdir -p .github/workflows
```

### 2. CI workflow (`.github/workflows/ci.yml`)
Runs on every push and pull request. Executes the backend test suite and a frontend type-check.

```yaml
name: CI

on:
  push:
    branches: [main, dev]
  pull_request:
    branches: [main, dev]

jobs:
  backend:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4

      - name: Set up Python
        uses: actions/setup-python@v5
        with:
          python-version: "3.12"

      - name: Install uv
        uses: astral-sh/setup-uv@v4

      - name: Install dependencies
        run: uv sync

      - name: Run tests
        working-directory: backend
        env:
          APP_ENV: test
          SECRET_KEY: ci-secret
          DATABASE_URL: sqlite+aiosqlite:///:memory:
          SUPABASE_URL: https://placeholder.supabase.co
          SUPABASE_SERVICE_ROLE_KEY: placeholder
          SUPABASE_JWT_SECRET: placeholder
          ANTHROPIC_API_KEY: placeholder
        run: uv run pytest -x

  frontend:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4

      - name: Set up Node
        uses: actions/setup-node@v4
        with:
          node-version: "20"
          cache: "npm"
          cache-dependency-path: frontend/package-lock.json

      - name: Install dependencies
        working-directory: frontend
        run: npm ci

      - name: Type check
        working-directory: frontend
        run: npm run build
```

### 3. Deploy workflow (`.github/workflows/deploy.yml`)
Triggers a Render deploy via webhook on merge to `dev` (staging) or `main` (production).

```yaml
name: Deploy

on:
  push:
    branches: [main, dev]

jobs:
  deploy:
    runs-on: ubuntu-latest
    steps:
      - name: Deploy to Render
        run: |
          if [ "${{ github.ref_name }}" = "main" ]; then
            HOOK_URL="${{ secrets.RENDER_DEPLOY_HOOK_PROD }}"
          else
            HOOK_URL="${{ secrets.RENDER_DEPLOY_HOOK_STAGING }}"
          fi
          curl -X POST "$HOOK_URL"
```

### 4. Add Render deploy hook URLs as GitHub secrets
In the Render dashboard for each service → **Settings → Deploy Hook** → copy the URL.

Add to GitHub → **Settings → Secrets and variables → Actions**:

| Secret | Value |
|---|---|
| `RENDER_DEPLOY_HOOK_PROD` | Deploy hook URL for the production Web Service |
| `RENDER_DEPLOY_HOOK_STAGING` | Deploy hook URL for the staging Web Service |

Do the same for the frontend Static Site if it doesn't auto-deploy from git.

### 5. Add any other CI secrets
Any env vars the test suite needs that aren't placeholders (e.g. a real staging Anthropic key) should be added as GitHub secrets and referenced in the workflow `env:` block.

---

## Branch protection (recommended)
In GitHub → **Settings → Branches**, add rules for `main` and `dev`:

- Require status checks to pass before merging (`CI / backend`, `CI / frontend`)
- Require pull request reviews before merging
- Do not allow direct pushes

This enforces the PR workflow from `/github-workflow` at the platform level.

---

## Verification
1. Open a PR to `dev` — the CI workflow should trigger and both jobs should pass.
2. Merge the PR — the deploy workflow should trigger and the Render service should redeploy.
3. Check Render logs (`/mcp-render`) to confirm the deploy completed successfully.
