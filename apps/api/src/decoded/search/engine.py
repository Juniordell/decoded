from __future__ import annotations

import time
from dataclasses import dataclass, field

import structlog
from openai import AsyncOpenAI
from qdrant_client import AsyncQdrantClient
from qdrant_client.models import FieldCondition, Filter, MatchAny
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from decoded.db.models import DecodedContent, Paper
from decoded.decoding.prompts import VERSION as PROMPT_VERSION
from decoded.embeddings.qdrant_setup import (
    ABSTRACTS_COLLECTION,
    CHUNKS_COLLECTION,
)
from decoded.search.reranker import Reranker

logger = structlog.get_logger()


@dataclass
class Candidate:
    """Um resultado bruto do Qdrant, antes do rerank."""
    arxiv_id: str
    text: str                    # o que vai pro reranker
    source: str                  # "abstract" | "chunk"
    section: str | None = None   # seção do paper, se veio de chunk
    vector_score: float = 0.0


@dataclass
class SearchResult:
    arxiv_id: str
    title: str
    one_sentence: str | None
    snippet: str | None
    section: str | None
    score: float
    published_at: object


@dataclass
class SearchOutcome:
    results: list[SearchResult] = field(default_factory=list)
    total_found: int = 0
    reranked: bool = False
    latency_ms: int = 0


class SearchEngine:
    def __init__(
        self,
        openai_api_key: str,
        qdrant_url: str,
        embedding_model: str,
        cohere_api_key: str | None = None,
        rerank_model: str = "rerank-v3.5",
    ) -> None:
        self._openai = AsyncOpenAI(api_key=openai_api_key)
        self._qdrant = AsyncQdrantClient(url=qdrant_url)
        self._embedding_model = embedding_model
        self._reranker = (
            Reranker(api_key=cohere_api_key, model=rerank_model)
            if cohere_api_key
            else None
        )

    async def close(self) -> None:
        await self._openai.close()
        await self._qdrant.close()

    async def __aenter__(self) -> "SearchEngine":
        return self

    async def __aexit__(self, *args) -> None:
        await self.close()

    # ---------------------------------------------------------------
    # 1. Retrieval
    # ---------------------------------------------------------------
    async def _embed_query(self, query: str) -> list[float]:
        resp = await self._openai.embeddings.create(
            model=self._embedding_model,
            input=[query],
        )
        return resp.data[0].embedding

    async def _retrieve(
        self,
        query_vec: list[float],
        k: int,
        categories: list[str] | None = None,
    ) -> list[Candidate]:
        """
        Busca nas duas coleções.

        Abstracts dão cobertura ampla (todo paper embedado tem um).
        Chunks dão precisão (o parágrafo exato que responde a pergunta).
        """
        qfilter = None
        if categories:
            qfilter = Filter(
                must=[
                    FieldCondition(
                        key="categories",
                        match=MatchAny(any=categories),
                    )
                ]
            )

        candidates: list[Candidate] = []
        seen_chunk_keys: set[tuple[str, int]] = set()

        # --- abstracts (vetor de 3072 dims) ---
        try:
            abs_resp = await self._qdrant.query_points(
                collection_name=ABSTRACTS_COLLECTION,
                query=query_vec,
                limit=k // 2,
                query_filter=qfilter,
                with_payload=True,
            )
            for point in abs_resp.points:
                payload = point.payload or {}
                candidates.append(
                    Candidate(
                        arxiv_id=payload.get("arxiv_id", ""),
                        text=payload.get("title", ""),
                        source="abstract",
                        vector_score=point.score,
                    )
                )
        except Exception as e:
            logger.warning("search.abstracts_failed", error=str(e))

        return candidates

    async def _retrieve_chunks(
        self,
        query: str,
        k: int,
        chunk_embedding_model: str,
    ) -> list[Candidate]:
        """
        Chunks usam text-embedding-3-small (1536 dims), então precisam de
        um embedding próprio da query — dimensões diferentes das abstracts.
        """
        resp = await self._openai.embeddings.create(
            model=chunk_embedding_model,
            input=[query],
        )
        chunk_vec = resp.data[0].embedding

        candidates: list[Candidate] = []
        try:
            chunk_resp = await self._qdrant.query_points(
                collection_name=CHUNKS_COLLECTION,
                query=chunk_vec,
                limit=k,
                with_payload=True,
            )
            for point in chunk_resp.points:
                payload = point.payload or {}
                candidates.append(
                    Candidate(
                        arxiv_id=payload.get("arxiv_id", ""),
                        text=payload.get("text", "")[:1500],
                        source="chunk",
                        section=payload.get("section"),
                        vector_score=point.score,
                    )
                )
        except Exception as e:
            logger.warning("search.chunks_failed", error=str(e))

        return candidates

    # ---------------------------------------------------------------
    # 2. Hidratação
    # ---------------------------------------------------------------
    async def _hydrate(
        self,
        session: AsyncSession,
        ranked: list[tuple[Candidate, float]],
    ) -> list[SearchResult]:
        """Busca título, one_sentence e metadata dos papers no Postgres."""
        arxiv_ids = list({c.arxiv_id for c, _ in ranked})
        if not arxiv_ids:
            return []

        # Papers
        stmt = select(Paper).where(Paper.arxiv_id.in_(arxiv_ids))
        papers = {p.arxiv_id: p for p in (await session.execute(stmt)).scalars().all()}

        # one_sentence de cada um
        paper_ids = [p.id for p in papers.values()]
        dc_stmt = select(DecodedContent).where(
            DecodedContent.paper_id.in_(paper_ids),
            DecodedContent.section == "one_sentence",
            DecodedContent.prompt_version == PROMPT_VERSION,
        )
        one_sentences: dict[int, str] = {}
        for row in (await session.execute(dc_stmt)).scalars().all():
            text = (row.content or {}).get("text")
            if text:
                one_sentences[row.paper_id] = text

        results: list[SearchResult] = []
        for candidate, score in ranked:
            paper = papers.get(candidate.arxiv_id)
            if paper is None:
                continue

            results.append(
                SearchResult(
                    arxiv_id=paper.arxiv_id,
                    title=paper.title,
                    one_sentence=one_sentences.get(paper.id),
                    snippet=candidate.text if candidate.source == "chunk" else None,
                    section=candidate.section,
                    score=score,
                    published_at=paper.published_at,
                )
            )

        return results

    # ---------------------------------------------------------------
    # 3. Orquestração
    # ---------------------------------------------------------------
    async def search(
        self,
        session: AsyncSession,
        query: str,
        retrieve_k: int = 40,
        return_k: int = 10,
        categories: list[str] | None = None,
        chunk_embedding_model: str = "text-embedding-3-small",
    ) -> SearchOutcome:
        start = time.perf_counter()
        log = logger.bind(query=query[:80])

        # --- Retrieval ---
        query_vec = await self._embed_query(query)
        abstract_candidates = await self._retrieve(query_vec, retrieve_k, categories)
        chunk_candidates = await self._retrieve_chunks(
            query, retrieve_k // 2, chunk_embedding_model
        )

        candidates = abstract_candidates + chunk_candidates

        # Dedup: um paper pode aparecer via abstract E via chunk.
        # Mantém a melhor evidência (chunk ganha, é mais específico).
        best_per_paper: dict[str, Candidate] = {}
        for c in candidates:
            if not c.arxiv_id or not c.text:
                continue
            existing = best_per_paper.get(c.arxiv_id)
            if existing is None:
                best_per_paper[c.arxiv_id] = c
            elif c.source == "chunk" and existing.source == "abstract":
                best_per_paper[c.arxiv_id] = c
            elif c.vector_score > existing.vector_score:
                best_per_paper[c.arxiv_id] = c

        deduped = list(best_per_paper.values())
        log.info(
            "search.retrieved",
            abstracts=len(abstract_candidates),
            chunks=len(chunk_candidates),
            deduped=len(deduped),
        )

        if not deduped:
            return SearchOutcome(
                latency_ms=int((time.perf_counter() - start) * 1000)
            )

        # --- Rerank ---
        reranked = False
        if self._reranker is not None:
            try:
                docs = [c.text for c in deduped]
                rr = await self._reranker.rerank(query, docs, top_n=return_k)
                ranked = [(deduped[r.index], r.relevance_score) for r in rr]
                reranked = True
                log.info("search.reranked", count=len(ranked))
            except Exception as e:
                log.warning("search.rerank_failed", error=str(e))
                ranked = sorted(
                    [(c, c.vector_score) for c in deduped],
                    key=lambda x: -x[1],
                )[:return_k]
        else:
            ranked = sorted(
                [(c, c.vector_score) for c in deduped],
                key=lambda x: -x[1],
            )[:return_k]

        # --- Hidratação ---
        results = await self._hydrate(session, ranked)

        latency_ms = int((time.perf_counter() - start) * 1000)
        log.info("search.done", results=len(results), latency_ms=latency_ms, reranked=reranked)

        return SearchOutcome(
            results=results,
            total_found=len(deduped),
            reranked=reranked,
            latency_ms=latency_ms,
        )