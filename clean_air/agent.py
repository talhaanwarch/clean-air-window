"""The planning agent: a versioned prompt, three tools, one traced tool loop.

The prompt lives in AcruxCore, and so does the list of tools it may call: each
tool is bound to the prompt in the dashboard. So the wording, the tools, and
the alias that rolls them out can all change without touching this code. The
code supplies only the functions that run the tools (`client_tools`). The model
call goes straight to OpenRouter with our own key (AcruxCore's BYO mode);
AcruxCore gets the trace. scripts/setup_acruxcore.py creates all of it once.
"""

from __future__ import annotations

from dataclasses import dataclass

from typing import Any, AsyncIterator

from pydantic import BaseModel, Field

import acruxcore as acrux

from . import config
from .tools import get_air_and_weather, get_local_air_news, search_health_guidance

PROVIDER: acrux.ProviderConfig = {"base_url": config.OPENROUTER_BASE_URL, "api_key": config.OPENROUTER_API_KEY}

# One line per paragraph: the dashboard editor wraps text itself, so hard line
# breaks here would show up as broken lines there.
SYSTEM_PROMPT = """You plan when someone should go outside today so they breathe the cleanest air.

Always call get_air_and_weather first. Then call search_health_guidance with the AQI category of the best window and who the person is, so your health advice comes from the EPA guidance and not from memory. Also call get_local_air_news for the city, because a smog alert or a school closure from this week can matter more than the forecast.

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
- local_news: one sentence about a headline from get_local_air_news that matters for going outside today, naming its source. Leave it empty when no headline matters or the search found none.
- news_title: the exact title of that headline, or empty.

Never invent numbers; use only what the tools return."""

USER_PROMPT = "When should I go out for my {{ activity }} today?"


# Tool name -> the function that runs it. The prompt's bindings decide which of
# these the model sees; a bound tool missing here fails before the first model call.
CLIENT_TOOLS = {
    "get_air_and_weather": get_air_and_weather,
    "search_health_guidance": search_health_guidance,
    "get_local_air_news": get_local_air_news,
}


class SetupMissing(RuntimeError):
    """The prompt has no tools bound, so the model would answer without any data."""


class PlanAnswer(BaseModel):
    """The typed answer the loop ends with, so the UI always gets the same parts."""

    why: str = Field(description="Why the best window beats the worst one, with their times and AQI.")
    for_you: str = Field(description="What the EPA guidance says this person should do.")
    source_title: str = Field(description="Exact title of the guidance passage used.")
    tip: str = Field(description="One practical tip for the activity.")
    local_news: str = Field(description="One sentence about a local headline that matters today, or empty.")
    news_title: str = Field(description="Exact title of that headline, or empty.")


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
    """Stream the agent's events: tool calls, tool results, text, then `done`.

    Raises SetupMissing when the prompt alias has no tools bound: run_prompt_with_tools
    would otherwise run it as a plain completion, and the model would make up a plan.
    """
    async with acrux.AcruxCore(api_key=config.ACRUXCORE_API_KEY, base_url=config.ACRUXCORE_BASE_URL) as hub:
        variables = request.variables()
        rendered = await hub.prompts.render(config.PROMPT_NAME, config.PROMPT_ALIAS, variables)
        if not rendered.tools:
            raise SetupMissing(
                f"The prompt '{config.PROMPT_NAME}' has no tools bound on '{config.PROMPT_ALIAS}'. "
                "Run scripts/setup_acruxcore.py."
            )
        stream = await hub.gateway.run_prompt_with_tools(
            rendered,
            model=config.CHAT_MODEL,
            client_tools=CLIENT_TOOLS,
            provider=PROVIDER,
            max_iterations=6,
            temperature=0.2,
            response_format=acrux.pydantic_response_format(PlanAnswer, name="plan_answer"),
            stream=True,
            trace={
                "name": "plan-outdoor-window",
                "session_id": session_id,
                "tags": ["clean-air-window", request.activity, config.PROMPT_ALIAS],
                "metadata": {"city": request.city, "model": config.CHAT_MODEL},
            },
        )
        async for event in stream:
            yield event
