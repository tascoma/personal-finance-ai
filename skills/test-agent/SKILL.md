---
name: "test-agent"
description: "Test Pydantic-AI agents in isolation by stubbing the model and asserting tool behavior"
metadata:
  author: agent-webapp-template
  version: 1.0.0
---

Test a Pydantic-AI agent without making real LLM calls: exercise tool logic directly, run the agent against a stub model, and override the agent dependency in route tests. Complements `/add-agent` (which defines the agent) and `/add-tests` (the pytest harness). Run from `backend/`.

## Design rule
Never make real model calls in tests — they are slow, costly, and non-deterministic. Test the two layers that matter separately: the **plain Python** behind each tool, and the **wiring** (does the agent call the right tool and return the right shape) using a stub model.

## Steps

### 1. Test tool logic as plain functions
Tools should delegate to plain functions (per `/add-agent`). Test those directly — no agent, no model. For a `@agent.tool_plain` like `get_current_time` in `backend/app/agents/agent.py`, call it and assert on the return:

```python
from app.agents.agent import get_current_time

def test_get_current_time_format():
    out = get_current_time()
    assert out.endswith("Z") and len(out) == 20  # ISO-8601 UTC
```

### 2. Run the agent against a stub model (`backend/tests/test_<name>_agent.py`)
Use pydantic-ai's `TestModel` to run the agent's full loop with no API call. `TestModel` automatically calls the agent's tools, so you can assert the run succeeds and tools fire. Use `agent.override(...)` so production code stays untouched.

```python
import pytest
from pydantic_ai.models.test import TestModel
from app.agents.<name> import agent

@pytest.mark.asyncio
async def test_agent_runs_with_stub_model():
    with agent.override(model=TestModel()):
        result = await agent.run("anything")
    assert result.output is not None
```

For an exact scripted reply or to assert a specific tool was called with specific args, use `FunctionModel` instead:

```python
from pydantic_ai.models.function import FunctionModel, AgentInfo
from pydantic_ai.messages import ModelResponse, TextPart

def stub(messages, info: AgentInfo) -> ModelResponse:
    return ModelResponse(parts=[TextPart("canned answer")])

async def test_agent_scripted_reply():
    with agent.override(model=FunctionModel(stub)):
        result = await agent.run("hi")
    assert result.output == "canned answer"
```

If the agent uses `result_type=MySchema`, assert `result.output` is an instance of that schema and its fields are populated.

### 3. Override the agent dependency in route tests
For a route that injects the agent via `get_<name>_agent` (from `/add-agent`), override the dependency so the endpoint runs against a stub:

```python
from app.main import app
from app.dependencies.<name> import get_<name>_agent
from pydantic_ai.models.test import TestModel
from app.agents.<name> import agent as real_agent

def stub_agent():
    with real_agent.override(model=TestModel()):
        return real_agent

app.dependency_overrides[get_<name>_agent] = stub_agent
# ... exercise the route with httpx.AsyncClient, then clear the override
```

Mock any external API the tools hit at the dependency layer — never inside the agent.

## Verification
Run from `backend/`:

```bash
uv run pytest tests/test_<name>_agent.py -v
```

Tests pass with no network calls. Confirm by running offline (or with `ANTHROPIC_API_KEY` unset) — stub-model tests still pass because no real model is contacted.
