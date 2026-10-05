"""Hourly air quality and weather from Open-Meteo, plus the best time windows.

Open-Meteo is free and needs no API key. The window ranking is plain arithmetic
done here, in code: the model gets ranked windows to reason about, instead of
adding up 24 hourly numbers itself.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import date as Date
from datetime import datetime

import httpx

GEOCODE_URL = "https://geocoding-api.open-meteo.com/v1/search"
FORECAST_URL = "https://api.open-meteo.com/v1/forecast"
AIR_URL = "https://air-quality-api.open-meteo.com/v1/air-quality"

# U.S. AQI categories, as defined by the EPA.
AQI_CATEGORIES = [
    (50, "Good"),
    (100, "Moderate"),
    (150, "Unhealthy for Sensitive Groups"),
    (200, "Unhealthy"),
    (300, "Very Unhealthy"),
    (10_000, "Hazardous"),
]


def aqi_category(aqi: float) -> str:
    """Name the EPA category an AQI value falls into."""
    for upper, name in AQI_CATEGORIES:
        if aqi <= upper:
            return name
    return "Hazardous"


@dataclass
class Place:
    name: str
    country: str
    latitude: float
    longitude: float


@dataclass
class Hour:
    time: datetime
    aqi: float
    pm2_5: float
    temperature: float
    feels_like: float
    rain_chance: float
    wind_kmh: float
    daylight: bool


@dataclass
class DayOutlook:
    place: Place
    day: Date
    sunrise: str
    sunset: str
    hours: list[Hour]


def geocode(city: str) -> Place:
    """Find a city's coordinates. Raises ValueError when nothing matches."""
    resp = httpx.get(GEOCODE_URL, params={"name": city, "count": 1}, timeout=15)
    resp.raise_for_status()
    results = resp.json().get("results") or []
    if not results:
        raise ValueError(f"No place called {city!r} was found.")
    top = results[0]
    return Place(top["name"], top.get("country", ""), top["latitude"], top["longitude"])


def fetch_day(city: str, day: Date | None = None) -> DayOutlook:
    """Fetch every hour of one local day (today by default) for a city."""
    place = geocode(city)
    coords = {"latitude": place.latitude, "longitude": place.longitude, "timezone": "auto", "forecast_days": 3}
    weather = httpx.get(
        FORECAST_URL,
        params={
            **coords,
            "hourly": "temperature_2m,apparent_temperature,precipitation_probability,wind_speed_10m,is_day",
            "daily": "sunrise,sunset",
        },
        timeout=15,
    )
    air = httpx.get(AIR_URL, params={**coords, "hourly": "us_aqi,pm2_5"}, timeout=15)
    weather.raise_for_status()
    air.raise_for_status()
    w, a = weather.json(), air.json()

    # Both APIs answer in the place's own time zone, so "today" is the first day returned.
    day = day or Date.fromisoformat(w["daily"]["time"][0])
    daily_index = w["daily"]["time"].index(day.isoformat())
    air_by_time = dict(zip(a["hourly"]["time"], zip(a["hourly"]["us_aqi"], a["hourly"]["pm2_5"])))

    hours: list[Hour] = []
    wh = w["hourly"]
    for i, stamp in enumerate(wh["time"]):
        moment = datetime.fromisoformat(stamp)
        if moment.date() != day or stamp not in air_by_time:
            continue
        aqi, pm = air_by_time[stamp]
        if aqi is None:
            continue
        hours.append(
            Hour(
                time=moment,
                aqi=float(aqi),
                pm2_5=float(pm or 0),
                temperature=wh["temperature_2m"][i],
                feels_like=wh["apparent_temperature"][i],
                rain_chance=float(wh["precipitation_probability"][i] or 0),
                wind_kmh=wh["wind_speed_10m"][i],
                daylight=bool(wh["is_day"][i]),
            )
        )
    return DayOutlook(
        place=place,
        day=day,
        sunrise=w["daily"]["sunrise"][daily_index][11:],
        sunset=w["daily"]["sunset"][daily_index][11:],
        hours=hours,
    )


def rank_windows(outlook: DayOutlook, free_from_hour: int, free_until_hour: int, duration_minutes: int) -> list[dict]:
    """Rank every window that starts at or after free_from_hour and ends by free_until_hour
    by the worst AQI inside it.

    The worst hour decides, not the average: one smoggy hour in the middle of a run
    is the hour that hurts. Windows with a likely shower or no daylight are kept but
    pushed down, because the person may still choose them.
    """
    span = max(1, math.ceil(duration_minutes / 60))
    by_hour = {h.time.hour: h for h in outlook.hours}
    windows = []
    for start in range(free_from_hour, free_until_hour - span + 1):
        block = [by_hour.get(start + k) for k in range(span)]
        if any(h is None for h in block):
            continue
        worst = max(h.aqi for h in block)
        rainy = max(h.rain_chance for h in block) >= 50
        dark = not all(h.daylight for h in block)
        windows.append(
            {
                "start": f"{start:02d}:00",
                "end": f"{(start + span) % 24:02d}:00",
                "worst_aqi": round(worst),
                "category": aqi_category(worst),
                "temperature_c": round(sum(h.temperature for h in block) / span),
                "rain_chance_pct": round(max(h.rain_chance for h in block)),
                "daylight": not dark,
                # Ties on the worst hour are common, so the average AQI and the heat
                # break them: a cooler, cleaner-on-average hour wins.
                "_score": worst
                + sum(h.aqi for h in block) / span / 100
                + (60 if rainy else 0)
                + (25 if dark else 0)
                + (15 if max(h.feels_like for h in block) >= 38 else 0),
            }
        )
    windows.sort(key=lambda w: w["_score"])
    for w in windows:
        del w["_score"]
    return windows
