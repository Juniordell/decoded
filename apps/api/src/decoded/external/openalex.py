from __future__ import annotations

from typing import Optional

import httpx
import structlog
from tenacity import retry, stop_after_attempt, wait_exponential

logger = structlog.get_logger()

OPENALEX_BASE = "https://api.openalex.org"


class OpenAlexClient:
    def __init__(self, email: str | None = None, timeout: float = 20.0) -> None:
        # Providing your email puts you in OpenAlex's "polite pool" — higher rate limits, priority
        headers = {"User-Agent": f"Decoded/0.1 (mailto:{email})" if email else "Decoded/0.1"}
        self._client = httpx.AsyncClient(
            base_url=OPENALEX_BASE,
            headers=headers,
            timeout=timeout,
        )

    async def close(self) -> None:
        await self._client.aclose()

    async def __aenter__(self) -> "OpenAlexClient":
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
        Resolve an arXiv ID to an OpenAlex Work.
        Returns a normalized dict or None if not found.
        """
        # OpenAlex indexes arxiv IDs like: https://arxiv.org/abs/2401.12345
        url_variant = f"https://arxiv.org/abs/{arxiv_id}"
        resp = await self._client.get(
            "/works",
            params={"filter": f"ids.openalex:https://openalex.org/W|doi.startswith:10.48550/arxiv.{arxiv_id}"},
        )
        # Try the DOI pattern arXiv uses (they mint DOIs now)
        resp = await self._client.get(
            "/works",
            params={"filter": f"doi:10.48550/arXiv.{arxiv_id}"},
        )

        if resp.status_code == 404:
            return None
        resp.raise_for_status()

        data = resp.json()
        results = data.get("results", [])
        if not results:
            return None

        work = results[0]
        return self._normalize(work)

    def _normalize(self, work: dict) -> dict:
        """Extract only what we care about from OpenAlex response."""
        return {
            "openalex_id": work.get("id"),
            "cited_by_count": work.get("cited_by_count", 0),
            "referenced_works_count": len(work.get("referenced_works", [])),
            "publication_year": work.get("publication_year"),
            "type": work.get("type"),
            "authorships": [
                {
                    "name": auth.get("author", {}).get("display_name"),
                    "openalex_id": auth.get("author", {}).get("id"),
                    "affiliation": (
                        auth.get("institutions", [{}])[0].get("display_name")
                        if auth.get("institutions")
                        else None
                    ),
                }
                for auth in work.get("authorships", [])
            ],
            "concepts": [
                {"name": c.get("display_name"), "score": c.get("score")}
                for c in work.get("concepts", [])[:5]
            ],
        }