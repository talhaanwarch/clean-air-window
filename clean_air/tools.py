"""The three tools the agent can call.

`@acrux.tool` builds each tool's JSON schema from the signature and docstring,
and the first run registers each one in the AcruxCore tool catalog. The functions
still run here, in this process: the catalog owns the definition the model
reads, and every call shows up as a tool span in the trace.
"""

from __future__ import annotations

import time
from functools import lru_cache

import acruxcore as acrux
import httpx

from .guidance import GuidanceIndex
from .open_meteo import DayOutlook, aqi_category, fetch_day, rank_windows
from .serpapi_news import recent_air_news

_OUTLOOK_TTL_SECONDS = 15 * 60


@lru_cache(maxsize=32)
def _cached_outlook(city: str, bucket: int) -> DayOutlook:
    return fetch_day(city)


def outlook_for(city: str) -> DayOutlook:
    """Today's outlook for a city, cached for 15 minutes so the chart and the tool agree."""
    return _cached_outlook(city.strip().lower(), int(time.time() // _OUTLOOK_TTL_SECONDS))


@lru_cache(maxsize=1)
def guidance_index() -> GuidanceIndex:
    """The guidance index, built once per process."""
    return GuidanceIndex()


@acrux.tool
async def get_air_and_weather(city: str, free_from_hour: int, free_until_hour: int, duration_minutes: int) -> dict:
    """Get today's hourly air quality (U.S. AQI) and weather for a city, and rank the
    time windows when the person is free from cleanest to dirtiest.

    Args:
        city: City name, for example 'Lahore'.
        free_from_hour: Earliest hour the person can start, 0-23 in local time.
        free_until_hour: Hour by which the person must be finished, 1-24 in local time.
        duration_minutes: How long the outdoor activity lasts.
    """
    outlook = outlook_for(city)
    windows = rank_windows(outlook, free_from_hour, free_until_hour, duration_minutes)
    worst = max(outlook.hours, key=lambda h: h.aqi)
    return {
        "place": f"{outlook.place.name}, {outlook.place.country}",
        "date": outlook.day.isoformat(),
        "sunrise": outlook.sunrise,
        "sunset": outlook.sunset,
        "best_window": windows[0] if windows else None,
        "next_best_windows": windows[1:3],
        "worst_window": max(windows, key=lambda w: w["worst_aqi"]) if windows else None,
        "worst_hour_of_day": {"hour": worst.time.strftime("%H:00"), "aqi": round(worst.aqi), "category": aqi_category(worst.aqi)},
        "hourly_aqi": {h.time.strftime("%H"): round(h.aqi) for h in outlook.hours},
    }


@acrux.tool
async def search_health_guidance(query: str) -> str:
    """Search official EPA / AirNow health guidance about air quality and outdoor
    activity. Use it to find what a given AQI level means for this person and what
    they should do. Cite the source title of any passage you rely on.

    Args:
        query: What to look up, for example 'asthma outdoor exercise AQI 160'.
    """
    hits = guidance_index().search(query, k=4)
    return "\n\n".join(f"[{i}] {chunk.title} ({chunk.url})\n{chunk.text}" for i, (chunk, _) in enumerate(hits, 1))


@acrux.tool
async def get_local_air_news(city: str) -> dict:
    """Get the last seven days of news headlines about air quality and smog in a city,
    newest first, such as official smog alerts or school closures. Use them only if a
    headline changes what the person should do today; many cities have none.

    Args:
        city: City name, for example 'Lahore'.
    """
    try:
        return {"city": city, "headlines": recent_air_news(city)}
    except (RuntimeError, httpx.HTTPError):
        # No key, or SerpApi refused (for example, the monthly quota is spent). The
        # error text is not passed on: an httpx error message carries the request
        # URL, and that URL holds the API key.
        return {"city": city, "headlines": [], "unavailable": "news search is unavailable right now"}
