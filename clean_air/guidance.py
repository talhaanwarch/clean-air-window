"""Search over the EPA / AirNow health guidance in data/guidance/ (the RAG part).

The corpus is about eighty chunks, so a numpy matrix and a dot product are the
whole vector store. Embeddings come from an open-weight model on OpenRouter,
and the index is cached on disk after the first build.
"""

from __future__ import annotations

import difflib
import hashlib
import re
from dataclasses import dataclass

import httpx
import numpy as np

from . import config

CHUNK_CHARS = 900
OVERLAP_CHARS = 150


@dataclass
class Chunk:
    title: str
    url: str
    text: str


def _load_documents() -> list[tuple[str, str, str]]:
    """Read every guidance file as (title, url, body)."""
    docs = []
    for path in sorted(config.GUIDANCE_DIR.glob("*.md")):
        raw = path.read_text()
        meta, body = raw.split("---\n", 2)[1:]
        fields = dict(line.split(": ", 1) for line in meta.strip().splitlines())
        docs.append((fields["title"], fields["url"], body.strip()))
    return docs


def _split(body: str) -> list[str]:
    """Cut a document into overlapping chunks, preferring paragraph breaks."""
    text = re.sub(r"\s*\n\s*", "\n", body)
    chunks, start = [], 0
    while start < len(text):
        end = min(len(text), start + CHUNK_CHARS)
        if end < len(text):
            cut = text.rfind("\n", start + CHUNK_CHARS // 2, end)
            end = cut if cut != -1 else end
        chunks.append(text[start:end].strip())
        if end == len(text):
            break
        start = end - OVERLAP_CHARS
    return [c for c in chunks if len(c) > 80]


def embed(texts: list[str]) -> np.ndarray:
    """Embed texts and return unit-length rows, so a dot product is cosine similarity."""
    resp = httpx.post(
        f"{config.OPENROUTER_BASE_URL}/embeddings",
        headers={"Authorization": f"Bearer {config.OPENROUTER_API_KEY}"},
        json={"model": config.EMBED_MODEL, "input": texts},
        timeout=120,
    )
    resp.raise_for_status()
    rows = sorted(resp.json()["data"], key=lambda r: r["index"])
    matrix = np.array([r["embedding"] for r in rows], dtype=np.float32)
    return matrix / np.linalg.norm(matrix, axis=1, keepdims=True)


class GuidanceIndex:
    """The chunks and their embeddings, rebuilt only when the corpus changes."""

    def __init__(self) -> None:
        self.chunks: list[Chunk] = [
            Chunk(title, url, piece) for title, url, body in _load_documents() for piece in _split(body)
        ]
        fingerprint = hashlib.sha256(
            (config.EMBED_MODEL + "".join(c.text for c in self.chunks)).encode()
        ).hexdigest()
        cached = np.load(config.INDEX_PATH) if config.INDEX_PATH.exists() else None
        if cached is not None and str(cached["fingerprint"]) == fingerprint:
            self.vectors = cached["vectors"]
        else:
            self.vectors = embed([c.text for c in self.chunks])
            np.savez(config.INDEX_PATH, vectors=self.vectors, fingerprint=fingerprint)

    def search(self, query: str, k: int = 4) -> list[tuple[Chunk, float]]:
        """Return the k chunks closest to the query, best first."""
        scores = self.vectors @ embed([query])[0]
        best = np.argsort(-scores)[:k]
        return [(self.chunks[i], float(scores[i])) for i in best]


def find_source(title: str) -> tuple[str, str] | None:
    """Match the title the model cited to a real guidance document, as (title, url).

    Models shorten or reword titles, so the closest title wins; a citation that
    matches nothing returns None and the UI shows no link rather than a wrong one.
    """
    docs = {doc_title: url for doc_title, url, _ in _load_documents()}
    match = difflib.get_close_matches(title, list(docs), n=1, cutoff=0.5)
    return (match[0], docs[match[0]]) if match else None
