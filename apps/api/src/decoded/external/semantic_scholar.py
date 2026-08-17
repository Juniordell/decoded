from __future__ import annotations

from typing import Optional

import httpx
import structlog
from tenacity import retry, stop_after_attempt, wait_exponential

logger = structlog.get_logger()

S2_BASE = "https://api.semanticscholar.org/graph/v1"


class SemanticScholarClient:
    def __init__(self, api_key: str | None = None, timeout: float = 20.0) -> None:
        headers = {}
        if api_key:
            headers["x-api-key"] = api_key
        self._client = httpx.AsyncClient(
            base_url=S2_BASE,
            headers=headers,
            timeout=timeout,
        )

    async def close(self) -> None:
        await self._client.aclose()

    async def __aenter__(self) -> "SemanticScholarClient":
        return self

    async def __aexit__(self, *args) -> None:
        await self.close()

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=2, max=15),
        reraise=True,
    )
    async def get_by_arxiv_id(self, arxiv_id: str) -> Optional[dict]:
        """
        Fetch paper by arXiv ID. Includes S2's TL;DR if available.
        """
        fields = "paperId,title,tldr,influentialCitationCount,citationCount,openAccessPdf,externalIds"
        resp = await self._client.get(
            f"/paper/arXiv:{arxiv_id}",
            params={"fields": fields},
        )
        if resp.status_code == 404:
            return None
        # S2 rate limits aggressively without an API key — 429s happen
        if resp.status_code == 429:
            logger.warning("s2.rate_limited", arxiv_id=arxiv_id)
            return None
        resp.raise_for_status()

        data = resp.json()
        return {
            "semantic_scholar_id": data.get("paperId"),
            "tldr": data.get("tldr", {}).get("text") if data.get("tldr") else None,
            "influential_citation_count": data.get("influentialCitationCount", 0),
            "citation_count": data.get("citationCount", 0),
            "open_access_pdf": data.get("openAccessPdf", {}).get("url"),
        }