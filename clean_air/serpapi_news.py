"""Recent local air-quality news from Google News, through SerpApi.

The EPA guidance says what an AQI level means; it cannot know that a city
closed its schools this morning. This module fills that gap with the last week
of headlines. Results are cached per city for six hours, because SerpApi's free
plan allows 250 searches a month and a public app would spend that in a day.
"""

from __future__ import annotations

import time
from datetime import datetime, timedelta, timezone

import httpx

from . import config

SEARCH_URL = "https://serpapi.com/search.json"
CACHE_SECONDS = 6 * 60 * 60
MAX_AGE = timedelta(days=7)
MAX_ITEMS = 5

_cache: dict[str, tuple[float, list[dict]]] = {}


def _parse_date(raw: str | None) -> datetime | None:
    """SerpApi dates look like '10/05/2026, 12:01 PM, +0000 UTC'."""
    if not raw:
        return None
    try:
        return datetime.strptime(raw.split(", +")[0], "%m/%d/%Y, %I:%M %p").replace(tzinfo=timezone.utc)
    except ValueError:
        return None


def recent_air_news(city: str) -> list[dict]:
    """Return up to five air-quality headlines for a city from the last seven days, newest first.

    Raises RuntimeError when no SerpApi key is configured, so the caller can tell
    the model the search is unavailable instead of reporting "no news".
    """
    if not config.SERPAPI_KEY:
        raise RuntimeError("SERPAPI_KEY is not set")
    key = city.strip().lower()
    cached = _cache.get(key)
    if cached and time.time() - cached[0] < CACHE_SECONDS:
        return cached[1]

    resp = httpx.get(
        SEARCH_URL,
        params={"engine": "google_news", "q": f"{city} air quality smog", "hl": "en", "api_key": config.SERPAPI_KEY},
        timeout=20,
    )
    resp.raise_for_status()
    cutoff = datetime.now(timezone.utc) - MAX_AGE
    items = []
    for row in resp.json().get("news_results", []):
        published = _parse_date(row.get("date"))
        if not published or published < cutoff or not row.get("link"):
            continue
        items.append(
            {
                "title": row.get("title", ""),
                "source": (row.get("source") or {}).get("name", ""),
                "published": published.strftime("%Y-%m-%d"),
                "link": row["link"],
            }
        )
    items.sort(key=lambda item: item["published"], reverse=True)
    items = items[:MAX_ITEMS]
    _cache[key] = (time.time(), items)
    return items
