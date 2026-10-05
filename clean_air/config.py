"""Settings read from the environment (or a local .env file)."""

from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent
load_dotenv(ROOT / ".env")

# AcruxCore keeps the prompt, the tool catalog and the traces.
ACRUXCORE_API_KEY = os.environ.get("ACRUXCORE_API_KEY", "")
ACRUXCORE_BASE_URL = os.environ.get("ACRUXCORE_BASE_URL", "http://localhost:3001/api/v1")

# Open-weight models, served by OpenRouter. Both Qwen models are Apache 2.0;
# ":nitro" asks OpenRouter for the fastest provider of the same weights.
OPENROUTER_BASE_URL = "https://openrouter.ai/api/v1"
OPENROUTER_API_KEY = os.environ.get("OPENROUTER_API_KEY", "")
CHAT_MODEL = os.environ.get("CHAT_MODEL", "qwen/qwen3-next-80b-a3b-instruct:nitro")
EMBED_MODEL = os.environ.get("EMBED_MODEL", "qwen/qwen3-embedding-8b")

PROMPT_NAME = "clean-air-window"
GUIDANCE_DIR = ROOT / "data" / "guidance"
# The embedding cache; override it to put the cache on a writable volume.
INDEX_PATH = Path(os.environ.get("INDEX_PATH", ROOT / "data" / "guidance-index.npz"))

# Where the "open this trace" link points: the AcruxCore dashboard.
ACRUXCORE_DASHBOARD_URL = os.environ.get("ACRUXCORE_DASHBOARD_URL", "http://localhost:8080")
