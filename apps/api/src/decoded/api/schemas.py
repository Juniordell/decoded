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

class TopicCard(BaseModel):
    """Versão de listagem."""

    slug: str
    name: str
    description: str | None = None
    keywords: list[str] = Field(default_factory=list)
    paper_count: int
    recent_papers: int = Field(
        default=0, description="Papers nas últimas 4 semanas"
    )
    momentum: float = Field(
        default=0.0, description="Variação relativa vs. as 4 semanas anteriores"
    )
    momentum_label: str = Field(default="steady")


class TopicPoint(BaseModel):
    """Um ponto na série temporal."""

    week: datetime
    papers: int
    citations: int
    mean_priority: float
    hn_mentions: int


class TopicAuthor(BaseModel):
    name: str
    affiliation: str | None = None
    paper_count: int
    total_citations: int


class TopicDetail(BaseModel):
    slug: str
    name: str
    description: str | None = None
    keywords: list[str] = Field(default_factory=list)
    paper_count: int

    recent_papers: int
    prior_papers: int
    momentum: float
    momentum_label: str

    timeline: list[TopicPoint] = Field(default_factory=list)
    top_authors: list[TopicAuthor] = Field(default_factory=list)
    papers: list[PaperCard] = Field(default_factory=list)

    last_clustered_at: datetime | None = None


class TopicsListResponse(BaseModel):
    topics: list[TopicCard]
    total: int
    clustered_at: datetime | None = None


class PulseResponse(BaseModel):
    """Visão geral do campo — a home do Field Pulse."""

    rising: list[TopicCard] = Field(default_factory=list)
    cooling: list[TopicCard] = Field(default_factory=list)
    emerging: list[TopicCard] = Field(default_factory=list)
    largest: list[TopicCard] = Field(default_factory=list)
    total_topics: int
    total_papers: int
    weeks_covered: int
    clustered_at: datetime | None = None