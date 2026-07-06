# CLAUDE.md

Template for building a React + FastAPI web app with a Pydantic-AI agent backend.

## Behavior

- **Simplicity first.** Prefer the smallest solution that works. No premature abstractions or speculative flexibility.
- **Test before closing.** Run or write a test for every change before reporting it done.
- **Follow best practices.** Match the conventions and patterns already in the codebase. When in doubt, prefer the idiomatic approach for the language or framework in use.

## Skills

Invoke these for step-by-step procedures. Each skill lives in `skills/<name>/SKILL.md`.

| Skill | When to use |
|---|---|
| `/setup` | First-time project bootstrap: venv, env, settings, logging, database, main.py (also documents the tech stack and project structure) |
| `/run-dev` | Run the backend and frontend locally together with hot reload |
| `/add-resource` | Add a full CRUD resource: model, schema, dep, service, router, tests |
| `/add-agent` | Add a new Pydantic-AI agent with tools and dependency wiring |
| `/setup-supabase` | Connect the app to a Supabase PostgreSQL database |
| `/setup-render` | Deploy the backend and frontend to Render |
| `/setup-ios` | Create the Xcode project and wire up the API client in `ios/` |
| `/add-ios-feature` | Add a new screen or feature to the iOS app |
| `/github-workflow` | Branch strategy, PR flow, and environment promotion |
| `/mcp-supabase` | Use the Supabase MCP to manage the database without leaving the editor |
| `/mcp-render` | Use the Render MCP to manage services and deployments without leaving the editor |
| `/setup-storage` | Set up Supabase Storage for file uploads |
| `/add-auth` | Add Supabase Auth: JWT verification, `current_user` dependency, protected routes, frontend and iOS auth flow |
| `/add-migration` | Set up Alembic and manage schema migrations |
| `/seed-database` | Write and run idempotent seed scripts for reference or test data |
| `/setup-frontend` | Wire up the React app: API client, env config, routing, auth state |
| `/add-frontend-feature` | Add a page or feature to the React frontend |
| `/add-tests` | Set up the pytest suite and write tests for a route module |
| `/test-frontend` | Set up Vitest + React Testing Library and write frontend tests |
| `/test-agent` | Test Pydantic-AI agents in isolation by stubbing the model |
| `/setup-ci` | Add GitHub Actions for CI and auto-deploy to Render |
| `/sync-skills` | Sync this repo's skills with the upstream template |
