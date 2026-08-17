"""HN Algolia — community signal (mentions of a paper on HN)."""

from __future__ import annotations

import httpx
import structlog
from tenacity import retry, stop_after_attempt, wait_exponential

logger = structlog.get_logger()

HN_BASE = "https://hn.algolia.com/api/v1"


class HackerNewsClient:
    def __init__(self, timeout: float = 15.0) -> None:
        self._client = httpx.AsyncClient(base_url=HN_BASE, timeout=timeout)

    async def close(self) -> None:
        await self._client.aclose()

    async def __aenter__(self) -> "HackerNewsClient":
        return self

    async def __aexit__(self, *args) -> None:
        await self.close()

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=2, max=15),
        reraise=True,
    )
    async def search_mentions(self, arxiv_id: str, title: str) -> dict:
        """
        Look for HN posts mentioning this paper.
        Returns count + top story info.
        """
        # First search by arxiv ID directly (link to arxiv.org/abs/{id})
        params = {
            "query": arxiv_id,
            "restrictSearchableAttributes": "url",
            "tags": "story",
            "hitsPerPage": 20,
        }
        resp = await self._client.get("/search", params=params)
        resp.raise_for_status()
        by_url = resp.json().get("hits", [])

        # Also search by title if it's distinctive enough
        by_title: list = []
        if len(title) > 20:
            resp2 = await self._client.get(
                "/search",
                params={
                    "query": title[:80],
                    "tags": "story",
                    "hitsPerPage": 5,
                },
            )
            resp2.raise_for_status()
            by_title = resp2.json().get("hits", [])

        # Dedupe by story ID
        seen: set = set()
        all_hits = []
        for hit in by_url + by_title:
            sid = hit.get("objectID")
            if sid and sid not in seen:
                seen.add(sid)
                all_hits.append(hit)

        total_points = sum(h.get("points", 0) or 0 for h in all_hits)
        top_story = max(all_hits, key=lambda h: h.get("points", 0) or 0, default=None)

        return {
            "mentions": len(all_hits),
            "total_points": total_points,
            "top_story_url": (
                f"https://news.ycombinator.com/item?id={top_story['objectID']}"
                if top_story
                else None
            ),
            "top_story_points": top_story.get("points") if top_story else 0,
        }