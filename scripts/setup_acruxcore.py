"""Create everything the app needs in AcruxCore. Safe to run again.

    python scripts/setup_acruxcore.py

1. Registers the three tools in the tool catalog, from their signatures and
   docstrings. An unchanged tool is left alone; a changed one gets a new version.
2. Creates the `clean-air-window` prompt with the template in clean_air/agent.py,
   on production. If the prompt exists and the template changed, it commits a new
   version but promotes nothing: you decide that in the dashboard.
3. Binds the three tools to the prompt, so every alias that has no bindings of
   its own calls all three.
"""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path

import acruxcore as acrux

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from clean_air import config  # noqa: E402
from clean_air.agent import CLIENT_TOOLS, SYSTEM_PROMPT, USER_PROMPT  # noqa: E402

MESSAGES = [{"role": "system", "content": SYSTEM_PROMPT}, {"role": "user", "content": USER_PROMPT}]


async def main() -> None:
    async with acrux.AcruxCore(api_key=config.ACRUXCORE_API_KEY, base_url=config.ACRUXCORE_BASE_URL) as hub:
        synced = await hub.tools.sync(list(CLIENT_TOOLS.values()))
        for name, result in zip(CLIENT_TOOLS, synced):
            state = "new version" if result.committed else "unchanged"
            print(f"tool   {name}: v{result.version_number} ({state})")

        found = [p for p in (await hub.prompts.list(search=config.PROMPT_NAME, limit=20)).data if p.name == config.PROMPT_NAME]
        if not found:
            prompt = await hub.prompts.create(
                config.PROMPT_NAME, description="Clean Air Window: picks the cleanest time to go outside today."
            )
            version = await hub.prompts.commit_version(prompt.id, MESSAGES)
            await hub.prompts.promote_alias(prompt.id, "production", version.version_number)
            print(f"prompt {config.PROMPT_NAME}: created v{version.version_number} on production")
            prompt_id = prompt.id
        else:
            prompt_id = found[0].id
            versions = (await hub.prompts.list_versions(prompt_id)).data
            latest = await hub.prompts.get_version(prompt_id, max(v.version_number for v in versions))
            current = [{"role": m["role"], "content": m["content"]} for m in latest.messages]
            if current == MESSAGES:
                print(f"prompt {config.PROMPT_NAME}: v{latest.version_number} matches the code")
            else:
                version = await hub.prompts.commit_version(prompt_id, MESSAGES)
                print(f"prompt {config.PROMPT_NAME}: committed v{version.version_number} (not promoted)")

        for name, result in zip(CLIENT_TOOLS, synced):
            await hub.prompts.set_tool_binding(prompt_id, result.tool_id, tool_alias="production")
            print(f"bind   {name} -> {config.PROMPT_NAME} (default, tool alias production)")


if __name__ == "__main__":
    asyncio.run(main())
