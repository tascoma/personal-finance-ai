---
name: "mcp-render"
description: "Use the Render MCP to manage services and deployments without leaving the editor"
metadata:
  author: agent-webapp-template
  version: 1.0.0
  mcp-server: render
---

Use the Render MCP tools to manage services and deployments directly from the editor — no dashboard required.

## When to use
Use these tools instead of the Render dashboard to inspect services, tail logs, update environment variables, trigger deploys, or check metrics during development and debugging.

Always orient first: select the right workspace, then list services to get the service IDs you'll need for other calls.

---

## Orient

**List workspaces and select the right one:**
```
mcp__render__list_workspaces
mcp__render__select_workspace
  workspaceId: "<id>"
```

**List all services in the selected workspace:**
```
mcp__render__list_services
```

Note the `id` for the services you'll be working with — it's required for most other calls.

**Get details for a specific service:**
```
mcp__render__get_service
  serviceId: "<id>"
```

---

## Deployments

**List recent deploys for a service:**
```
mcp__render__list_deploys
  serviceId: "<id>"
```

**Get the status and details of a specific deploy:**
```
mcp__render__get_deploy
  serviceId: "<id>"
  deployId: "<id>"
```

After merging a PR to `dev` or `main`, use these to confirm the auto-deploy triggered and check whether it succeeded.

---

## Logs

**Tail logs for a service** (useful for debugging startup errors and runtime issues):
```
mcp__render__list_logs
  serviceId: "<id>"
```

**List available log label values** (to filter logs by label):
```
mcp__render__list_log_label_values
  serviceId: "<id>"
```

---

## Environment variables

**Update environment variables for a service** — pass the full set of key/value pairs you want to set or update:
```
mcp__render__update_environment_variables
  serviceId: "<id>"
  envVars: [{ "key": "LOG_LEVEL", "value": "DEBUG" }]
```

This replaces individual variables without touching others. Use it to promote config changes (e.g. pointing the staging service at a new Supabase branch URL) without a full redeployment.

---

## Update service settings

**Update a web service** (instance type, build/start command, health check path, etc.):
```
mcp__render__update_web_service
  serviceId: "<id>"
  ...fields to update
```

**Update a static site** (build command, publish path, redirects):
```
mcp__render__update_static_site
  serviceId: "<id>"
  ...fields to update
```

---

## Metrics

**Get CPU, memory, and request metrics for a service:**
```
mcp__render__get_metrics
  serviceId: "<id>"
```

Check metrics after a deploy or when investigating a performance issue before touching any code.

---

## PostgreSQL (Render-managed databases)

If the project uses a Render Postgres instance instead of Supabase:

```
mcp__render__list_postgres_instances
mcp__render__get_postgres
  postgresId: "<id>"
mcp__render__query_render_postgres
  postgresId: "<id>"
  query: "SELECT * FROM users LIMIT 5;"
```

For this project, Supabase is the primary database — use these only if a Render Postgres instance has been provisioned separately.

---

## Key-value store

Render provides a native key-value store (Redis-compatible):

```
mcp__render__list_key_value
mcp__render__get_key_value
  keyValueId: "<id>"
mcp__render__create_key_value
```

---

## Rules
- Always select the correct workspace before acting — mistakes against the wrong workspace affect production.
- When updating environment variables on the production service, double-check the `serviceId` is the prod service, not staging.
- Use `list_deploys` + `get_deploy` to verify a deploy succeeded before reporting a change as live.
- Check `list_logs` immediately after a failed deploy — the error is almost always in the startup output.
