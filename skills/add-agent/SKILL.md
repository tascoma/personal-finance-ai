---
name: "add-agent"
description: "Add a new Pydantic-AI agent with tools and dependency wiring"
metadata:
  author: agent-webapp-template
  version: 1.0.0
---

Add a new Pydantic-AI agent: define it in `agents/`, wire its API key from settings, expose it through a dependency factory, and keep tools thin.

## Design rule
Deterministic logic must not be delegated to the LLM. If a step can be expressed as plain Python (parsing, filtering, math, lookups, conditionals), implement it as a regular function and call it from a tool or service. Only use the LLM for steps that genuinely require language understanding, inference, or judgment. Agent tools should validate inputs, call a plain function, and return a structured result.

## Steps

### 1. Agent definition (`backend/app/agents/<name>.py`)
Define the agent. Wire the model and API key from `settings`. Use `@agent.tool_plain` for tools that don't need injected dependencies; use `@agent.tool` when the tool needs `RunContext` (e.g. to access `deps`).

```python
from pydantic_ai import Agent, RunContext
from app.core.config import settings

agent = Agent(
    model=f"anthropic:{settings.anthropic_model}",
    system_prompt="...",
)

# For tools with no agent-injected dependencies:
@agent.tool_plain
def my_tool(arg: str) -> str:
    return _compute(arg)  # delegate to a plain function

# For tools that need deps injected via Agent(deps_type=MyDeps):
@agent.tool
async def my_tool_with_deps(ctx: RunContext[MyDeps], arg: str) -> str:
    return await ctx.deps.some_service.do_thing(arg)
```

If the agent needs structured output, pass `result_type=MyResponseSchema` to `Agent(...)`.

### 2. Dependency factory (`backend/app/dependencies/<name>.py`)
Expose the agent through a `Depends()`-compatible factory so routes receive it via injection and tests can swap it.

```python
from app.agents.<name> import agent
from pydantic_ai import Agent

def get_<name>_agent() -> Agent:
    return agent
```

If the agent uses `deps_type`, build and inject the deps object here too.

### 3. Use in a route or service
Inject the agent via `Depends()` in the route, pass it to the service.

```python
from app.dependencies.<name> import get_<name>_agent

@router.post("/run")
async def run_agent(
    payload: RunRequest,
    agent = Depends(get_<name>_agent),
):
    result = await agent.run(payload.prompt)
    return {"output": result.data}
```

### 4. Tests (`backend/tests/test_<name>_agent.py`)
Override the dependency in tests to inject a stub or a fixture agent with a test model. Test tool logic by calling the plain functions directly — no LLM call needed.

```python
from app.main import app
from app.dependencies.<name> import get_<name>_agent

def override_agent():
    return stub_agent  # a minimal Agent pointed at a test model

app.dependency_overrides[get_<name>_agent] = override_agent
```

## Verification
Run from `backend/`:

```bash
uv run pytest tests/test_<name>_agent.py -v
```

Confirm the route returns the expected schema. If the agent calls external APIs, mock at the dependency layer, not inside the agent itself.
