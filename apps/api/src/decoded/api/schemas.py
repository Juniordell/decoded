from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field


class AuthorOut(BaseModel):
    name: str
    affiliation: str | None = None


class PaperCard(BaseModel):
    """Versão resumida — usada no feed."""

    arxiv_id: str
    title: str
    one_sentence: str | None = Field(
        default=None,
        description="Resumo de uma frase, se o paper já foi decodificado",
    )
    authors: list[str] = Field(default_factory=list)
    published_at: datetime
    categories: list[str] = Field(default_factory=list)
    priority_score: float
    citation_count: int
    hn_mentions: int
    is_decoded: bool
    decoded_sections: list[str] = Field(default_factory=list)


class PaperDetail(BaseModel):
    """Versão completa — usada na página do paper."""

    arxiv_id: str
    title: str
    abstract: str
    authors: list[AuthorOut] = Field(default_factory=list)
    published_at: datetime
    categories: list[str] = Field(default_factory=list)
    pdf_url: str
    priority_score: float
    citation_count: int
    hn_mentions: int
    hn_url: str | None = None

    # Conteúdo decodificado, por seção
    decoded: dict[str, dict] = Field(
        default_factory=dict,
        description="Mapa de nome_da_seção → conteúdo JSON",
    )
    decoded_at: datetime | None = None


class FeedResponse(BaseModel):
    papers: list[PaperCard]
    total: int
    has_more: bool
    next_cursor: str | None = None


class SearchHit(BaseModel):
    arxiv_id: str
    title: str
    one_sentence: str | None = None
    snippet: str | None = Field(
        default=None,
        description="Trecho do paper que casou com a busca",
    )
    section: str | None = Field(
        default=None,
        description="Seção do paper de onde veio o trecho",
    )
    score: float
    published_at: datetime


class SearchResponse(BaseModel):
    query: str
    hits: list[SearchHit]
    total_found: int
    reranked: bool
    latency_ms: int