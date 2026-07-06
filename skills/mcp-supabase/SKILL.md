---
name: "mcp-supabase"
description: "Use the Supabase MCP to manage the database without leaving the editor"
metadata:
  author: agent-webapp-template
  version: 1.0.0
  mcp-server: supabase
---

Use the Supabase MCP tools to manage the database directly from the editor — no dashboard required.

## When to use
Use these tools instead of the Supabase dashboard whenever you need to inspect schema, run migrations, query data, or debug issues during development.

Always check the current state before making changes: list tables, check existing migrations, read advisors.

---

## Reference schema and state

**List all tables in the project:**
```
mcp__supabase__list_tables
```

**List applied migrations:**
```
mcp__supabase__list_migrations
```

**List available extensions:**
```
mcp__supabase__list_extensions
```

**Check the project URL (needed for client config):**
```
mcp__supabase__get_project_url
```

**Get publishable API keys (anon key for frontend clients):**
```
mcp__supabase__get_publishable_keys
```

---

## Run and manage migrations

**Apply a new migration** — write the SQL and give it a descriptive name:
```
mcp__supabase__apply_migration
  name: "create_users_table"
  query: "CREATE TABLE users (id uuid PRIMARY KEY DEFAULT gen_random_uuid(), ...);"
```

Migration names must be unique and follow the existing naming convention in the project.

**Execute arbitrary SQL** (for one-off queries, data checks, or debugging — not for schema changes):
```
mcp__supabase__execute_sql
  query: "SELECT * FROM users LIMIT 10;"
```

Use `apply_migration` for schema changes and `execute_sql` for read-only queries or ad-hoc data fixes.

---

## Debug and audit

**Fetch recent logs** (API, auth, storage, postgres, edge functions):
```
mcp__supabase__get_logs
  service: "postgres"
```

**Run the advisor** to surface performance, security, and schema issues:
```
mcp__supabase__get_advisors
```

Run advisors before and after applying migrations to catch problems early.

---

## Supabase branches (preview environments)

Supabase branches let you create an isolated database environment for a feature branch — staging and production remain untouched.

**Create a branch** when starting a feature that involves schema changes:
```
mcp__supabase__create_branch
  name: "feature/add-users-table"
```

**List active branches:**
```
mcp__supabase__list_branches
```

**Reset a branch** back to its base migration state if you want a clean slate:
```
mcp__supabase__reset_branch
  branch_id: "<id>"
```

**Merge a branch** into the main project when the feature is ready:
```
mcp__supabase__merge_branch
  branch_id: "<id>"
```

**Delete a branch** after it's merged:
```
mcp__supabase__delete_branch
  branch_id: "<id>"
```

---

## Generate TypeScript types

After schema changes, regenerate types for the frontend or iOS app:
```
mcp__supabase__generate_typescript_types
```

Copy the output into `frontend/src/types/supabase.ts` (or the equivalent location in your project).

---

## Search the Supabase docs

Look up Supabase features or APIs without leaving the editor:
```
mcp__supabase__search_docs
  query: "row level security policies"
```

---

## Rules
- Use `apply_migration` for all schema changes — never alter the schema via raw `execute_sql` in production.
- Always run `get_advisors` after a significant migration.
- Supabase branches are tied to the staging environment. Use them for feature work involving schema changes; merge the branch to Supabase before merging the PR to `dev`.
- Never run destructive SQL (`DROP TABLE`, `DELETE FROM` without a `WHERE`) against the production project.
