"""Settings read from the environment (or a local .env file)."""

from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent
load_dotenv(ROOT / ".env")

# AcruxCore keeps the prompt, the tool catalog and the traces.
ACRUXCORE_API_KEY = os.environ.get("ACRUXCORE_API_KEY", "")
ACRUXCORE_BASE_URL = os.environ.get("ACRUXCORE_BASE_URL", "https://api.acruxcore.com/api/v1")

# Open-weight models, served by OpenRouter: Gemma 4 for chat and Qwen3 for
# embeddings, both Apache 2.0;
# ":nitro" asks OpenRouter for the fastest provider of the same weights.
OPENROUTER_BASE_URL = "https://openrouter.ai/api/v1"
OPENROUTER_API_KEY = os.environ.get("OPENROUTER_API_KEY", "")
CHAT_MODEL = os.environ.get("CHAT_MODEL", "google/gemma-4-31b-it:nitro")
EMBED_MODEL = os.environ.get("EMBED_MODEL", "qwen/qwen3-embedding-8b")

PROMPT_NAME = "clean-air-window"
GUIDANCE_DIR = ROOT / "data" / "guidance"
# The embedding cache; override it to put the cache on a writable volume.
INDEX_PATH = Path(os.environ.get("INDEX_PATH", ROOT / "data" / "guidance-index.npz"))

# Where the "open this trace" link points: the AcruxCore dashboard.
ACRUXCORE_DASHBOARD_URL = os.environ.get("ACRUXCORE_DASHBOARD_URL", "https://acruxcore.com")

# SerpApi key for the local-news tool; without it the tool reports that it is off.
SERPAPI_KEY = os.environ.get("SERPAPI_KEY", "")

# Spending guards for a public deployment: plans per browser session, and plans
# per day for the whole server. Each plan is one OpenRouter run and may be one search.
SESSION_PLAN_LIMIT = int(os.environ.get("SESSION_PLAN_LIMIT", "5"))
DAILY_PLAN_LIMIT = int(os.environ.get("DAILY_PLAN_LIMIT", "150"))

# Which prompt alias the app runs. "staging" lets a new prompt version and its
# tools be tried before production gets them.
PROMPT_ALIAS = os.environ.get("PROMPT_ALIAS", "production")
