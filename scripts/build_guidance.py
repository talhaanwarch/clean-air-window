"""Download the health guidance the agent cites, and save it as plain markdown.

Every source is a U.S. EPA / AirNow publication, which is public domain, so the
extracted text can live in this repo. Run it again to refresh the copies:

    python scripts/build_guidance.py
"""

from __future__ import annotations

import io
import re
from pathlib import Path

import httpx
import trafilatura
from pypdf import PdfReader

OUT_DIR = Path(__file__).resolve().parent.parent / "data" / "guidance"

SOURCES = [
    {
        "slug": "epa-air-quality-guide-particle-pollution",
        "title": "EPA — Air Quality Guide for Particle Pollution",
        "url": "https://www.airnow.gov/sites/default/files/2023-03/air-quality-guide-for-particle-pollution_0.pdf",
    },
    {
        "slug": "epa-guide-to-air-quality-and-your-health",
        "title": "EPA — Air Quality Index: A Guide to Air Quality and Your Health (2014)",
        "url": "https://www.airnow.gov/sites/default/files/2018-04/aqi_brochure_02_14_0.pdf",
    },
    {
        "slug": "airnow-aqi-basics",
        "title": "AirNow — Air Quality Index (AQI) Basics",
        "url": "https://www.airnow.gov/aqi/aqi-basics/",
    },
    {
        "slug": "airnow-your-health",
        "title": "AirNow — Your Health",
        "url": "https://www.airnow.gov/air-quality-and-health/your-health/",
    },
    {
        "slug": "epa-patient-exposure-and-aqi",
        "title": "EPA — Patient Exposure and the Air Quality Index",
        "url": "https://www.epa.gov/pmcourse/patient-exposure-and-air-quality-index",
    },
]


def extract(url: str, body: bytes) -> str:
    """Turn a PDF or an HTML page into readable text."""
    if url.endswith(".pdf"):
        pages = PdfReader(io.BytesIO(body)).pages
        text = "\n".join(page.extract_text() or "" for page in pages)
    else:
        text = trafilatura.extract(body.decode("utf-8", "replace"), include_tables=True, output_format="markdown") or ""
    # PDFs break lines mid-sentence; collapse runs of spaces and blank lines.
    text = re.sub(r"[ \t]+", " ", text)
    return re.sub(r"\n{3,}", "\n\n", text).strip()


def main() -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    with httpx.Client(follow_redirects=True, timeout=30, headers={"User-Agent": "Mozilla/5.0"}) as http:
        for source in SOURCES:
            resp = http.get(source["url"])
            resp.raise_for_status()
            text = extract(source["url"], resp.content)
            header = f"---\ntitle: {source['title']}\nurl: {source['url']}\n---\n\n"
            (OUT_DIR / f"{source['slug']}.md").write_text(header + text + "\n")
            print(f"{len(text):>6} chars  {source['slug']}")


if __name__ == "__main__":
    main()
