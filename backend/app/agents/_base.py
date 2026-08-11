"""Shared agent factory + runner.

All Pydantic-AI agents in this package share the same model/provider wiring and
the same "log on failure, log on success, re-raise" pattern around `agent.run`.
This module centralizes both so each agent module stays focused on its prompt
and output schema.
"""

import logging
from typing import Any

from pydantic import BaseModel
from pydantic_ai import Agent
from pydantic_ai.models.anthropic import AnthropicModel
from pydantic_ai.providers.anthropic import AnthropicProvider

from app.core.config import settings

logger = logging.getLogger("app.agents")


class AgentError(Exception):
    """Raised by `run_agent` when the underlying LLM call fails.

    Wraps the original exception so route layers can catch a single, narrow
    type instead of bare `Exception`.
    """


def build_agent[TOutput: BaseModel](
    output_type: type[TOutput], system_prompt: str
) -> Agent[None, TOutput]:
    return Agent(
        AnthropicModel(
            settings.anthropic_model,
            provider=AnthropicProvider(api_key=settings.anthropic_api_key),
        ),
        output_type=output_type,
        system_prompt=system_prompt,
    )


async def run_agent[TOutput: BaseModel](
    agent: Agent[None, TOutput],
    name: str,
    prompt: Any,
) -> TOutput:
    logger.debug("Running %s", name)
    try:
        result = await agent.run(prompt)
    except Exception as exc:
        logger.exception("%s failed", name)
        raise AgentError(f"{name} failed: {exc}") from exc
    logger.debug("%s succeeded", name)
    return result.output
