"""The planning agent: a versioned prompt, two tools, one traced tool loop.

The prompt lives in AcruxCore, so its wording can be edited and promoted from
the dashboard without touching this code. The model call goes straight to
OpenRouter with our own key (AcruxCore's BYO mode); AcruxCore gets the trace.
"""

from __future__ import annotations

from dataclasses import dataclass

from pydantic import BaseModel, Field
from typing import Any, AsyncIterator

import acruxcore as acrux

from . import config
from .tools import get_air_and_weather, search_health_guidance

PROVIDER: acrux.ProviderConfig = {"base_url": config.OPENROUTER_BASE_URL, "api_key": config.OPENROUTER_API_KEY}

# One line per paragraph: the dashboard editor wraps text itself, so hard line
# breaks here would show up as broken lines there.
SYSTEM_PROMPT = """You plan when someone should go outside today so they breathe the cleanest air.

Always call get_air_and_weather first. Then call search_health_guidance with the AQI category of the best window and who the person is, so your health advice comes from the EPA guidance and not from memory.

The person:
- City: {{ city }}
- Activity: {{ activity }} for {{ duration_minutes }} minutes
- Free between {{ free_from_hour }}:00 and {{ free_until_hour }}:00
{% if sensitive_groups %}- Belongs to an EPA sensitive group: {{ sensitive_groups }}
{% else %}- Healthy adult, not in a sensitive group
{% endif %}
The app already shows the chosen time, its AQI and an hourly chart, taken from best_window. Your job is the explanation, in short plain sentences:

- why: compare best_window with worst_window, using their exact times and AQI numbers as the tool gave them. If best_window is Unhealthy or worse, say plainly that even the best time is not clean.
- for_you: what the EPA guidance says this person should do at the best window's AQI category.
- source_title: the exact title of the guidance passage you used.
- tip: one practical tip for this activity, such as going shorter, lighter, or taking breaks. Suggest an easier version rather than staying inside.

Never invent numbers; use only what the tools return."""

USER_PROMPT = "When should I go out for my {{ activity }} today?"


async def ensure_prompt(hub: acrux.AcruxCore) -> None:
    """Create the prompt with version 1 on production, unless it already exists.

    An existing prompt is left alone: once it is created, the dashboard owns it.
    """
    found = await hub.prompts.list(search=config.PROMPT_NAME, limit=20)
    if any(p.name == config.PROMPT_NAME for p in found.data):
        return
    prompt = await hub.prompts.create(config.PROMPT_NAME, description="Clean Air Window: picks the cleanest time to go outside today.")
    version = await hub.prompts.commit_version(
        prompt.id,
        [{"role": "system", "content": SYSTEM_PROMPT}, {"role": "user", "content": USER_PROMPT}],
    )
    await hub.prompts.promote_alias(prompt.id, "production", version.version_number)


class PlanAnswer(BaseModel):
    """The typed answer the loop ends with, so the UI always gets the same four parts."""

    why: str = Field(description="Why the best window beats the worst one, with their times and AQI.")
    for_you: str = Field(description="What the EPA guidance says this person should do.")
    source_title: str = Field(description="Exact title of the guidance passage used.")
    tip: str = Field(description="One practical tip for the activity.")


@dataclass
class PlanRequest:
    city: str
    activity: str
    duration_minutes: int
    free_from_hour: int
    free_until_hour: int
    sensitive_groups: list[str]

    def variables(self) -> dict[str, Any]:
        # One string, not a list, so the template needs no filter to print it.
        return {**self.__dict__, "sensitive_groups": ", ".join(self.sensitive_groups)}


async def plan(request: PlanRequest, session_id: str | None = None) -> AsyncIterator[acrux.ToolLoopEvent]:
    """Stream the agent's events: tool calls, tool results, text, then `done`."""
    async with acrux.AcruxCore(api_key=config.ACRUXCORE_API_KEY, base_url=config.ACRUXCORE_BASE_URL) as hub:
        await ensure_prompt(hub)
        variables = request.variables()
        rendered = await hub.prompts.render(config.PROMPT_NAME, "production", variables)
        stream = await hub.gateway.run_tool_loop(
            config.CHAT_MODEL,
            rendered.messages,
            tools=[get_air_and_weather, search_health_guidance],
            provider=PROVIDER,
            prompt_version_id=rendered.version_id,
            variables=variables,
            max_iterations=6,
            temperature=0.2,
            response_format=acrux.pydantic_response_format(PlanAnswer, name="plan_answer"),
            stream=True,
            trace={
                "name": "plan-outdoor-window",
                "session_id": session_id,
                "tags": ["clean-air-window", request.activity],
                "metadata": {"city": request.city, "model": config.CHAT_MODEL},
            },
        )
        async for event in stream:
            yield event
