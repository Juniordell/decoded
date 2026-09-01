from datetime import datetime
from enum import Enum
from typing import Optional

from sqlalchemy import (
    ARRAY,
    JSON,
    Boolean,
    Column,
    DateTime,
    Enum as SQLEnum,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Table,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from decoded.db.base import Base


# ============================================================
# Enums
# ============================================================
class IngestionStatus(str, Enum):
    PENDING = "pending"
    FETCHED = "fetched"
    ENRICHED = "enriched"
    PARSED = "parsed"
    EMBEDDED = "embedded"
    DECODED = "decoded"
    FAILED = "failed"


class RunStatus(str, Enum):
    RUNNING = "running"
    SUCCESS = "success"
    FAILED = "failed"


# ============================================================
# Association tables (many-to-many)
# ============================================================
paper_authors = Table(
    "paper_authors",
    Base.metadata,
    Column("paper_id", ForeignKey("papers.id", ondelete="CASCADE"), primary_key=True),
    Column("author_id", ForeignKey("authors.id", ondelete="CASCADE"), primary_key=True),
    Column("position", Integer, nullable=False),  # author order on the paper
)

paper_topics = Table(
    "paper_topics",
    Base.metadata,
    Column("paper_id", ForeignKey("papers.id", ondelete="CASCADE"), primary_key=True),
    Column("topic_id", ForeignKey("topics.id", ondelete="CASCADE"), primary_key=True),
    Column("confidence", Float, nullable=False, default=1.0),
)


# ============================================================
# Papers
# ============================================================
class Paper(Base):
    __tablename__ = "papers"

    id: Mapped[int] = mapped_column(primary_key=True)
    arxiv_id: Mapped[str] = mapped_column(String(50), unique=True, index=True)

    title: Mapped[str] = mapped_column(Text, nullable=False)
    abstract: Mapped[str] = mapped_column(Text, nullable=False)

    # arXiv fields
    published_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    arxiv_updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    pdf_url: Mapped[str] = mapped_column(Text, nullable=False)
    categories: Mapped[list[str]] = mapped_column(ARRAY(String), nullable=False, default=list)

    # Enrichment
    openalex_id: Mapped[Optional[str]] = mapped_column(String(100), nullable=True, index=True)
    semantic_scholar_id: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    citation_count: Mapped[int] = mapped_column(Integer, default=0)
    hn_mentions: Mapped[int] = mapped_column(Integer, default=0)
    priority_score: Mapped[float] = mapped_column(Float, default=0.0, index=True)

    # Pipeline state
    status: Mapped[IngestionStatus] = mapped_column(
        SQLEnum(IngestionStatus, name="ingestion_status"),
        default=IngestionStatus.PENDING,
        index=True,
    )

    # Free-form metadata
    extra: Mapped[dict] = mapped_column(JSON, default=dict)

    # Relationships
    authors: Mapped[list["Author"]] = relationship(
        secondary=paper_authors,
        back_populates="papers",
        order_by="paper_authors.c.position",
    )
    topics: Mapped[list["Topic"]] = relationship(
        secondary=paper_topics,
        back_populates="papers",
    )
    parsed_content: Mapped[Optional["ParsedContent"]] = relationship(
        back_populates="paper",
        uselist=False,
        cascade="all, delete-orphan",
    )

    __table_args__ = (
        Index("ix_papers_published_at", "published_at"),
        Index("ix_papers_priority_status", "priority_score", "status"),
    )


# ============================================================
# Authors
# ============================================================
class Author(Base):
    __tablename__ = "authors"

    id: Mapped[int] = mapped_column(primary_key=True)

    # Chave de desambiguação. Quando presente, é confiável.
    openalex_id: Mapped[Optional[str]] = mapped_column(
        String(100), unique=True, nullable=True, index=True
    )
    # Fallback: nome normalizado. Usado quando não há openalex_id.
    normalized_name: Mapped[str] = mapped_column(String(300), index=True)

    slug: Mapped[str] = mapped_column(String(160), unique=True, index=True)
    name: Mapped[str] = mapped_column(String(300), nullable=False, index=True)

    affiliation: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    institution_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("institutions.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )

    h_index: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    total_citations: Mapped[int] = mapped_column(Integer, default=0)
    paper_count: Mapped[int] = mapped_column(Integer, default=0)

    # True quando veio da OpenAlex; False quando é agrupamento por nome
    is_disambiguated: Mapped[bool] = mapped_column(Boolean, default=False)

    papers: Mapped[list["Paper"]] = relationship(
        secondary=paper_authors,
        back_populates="authors",
    )
    institution: Mapped[Optional["Institution"]] = relationship(
        back_populates="authors"
    )

    __table_args__ = (
        Index("ix_authors_paper_count", "paper_count"),
    )


class Institution(Base):
    __tablename__ = "institutions"

    id: Mapped[int] = mapped_column(primary_key=True)

    openalex_id: Mapped[Optional[str]] = mapped_column(
        String(100), unique=True, nullable=True, index=True
    )
    slug: Mapped[str] = mapped_column(String(160), unique=True, index=True)
    name: Mapped[str] = mapped_column(String(400), nullable=False, index=True)

    country_code: Mapped[Optional[str]] = mapped_column(String(4), nullable=True)
    institution_type: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)

    paper_count: Mapped[int] = mapped_column(Integer, default=0)
    author_count: Mapped[int] = mapped_column(Integer, default=0)
    total_citations: Mapped[int] = mapped_column(Integer, default=0)

    authors: Mapped[list[Author]] = relationship(back_populates="institution")

    __table_args__ = (
        Index("ix_institutions_paper_count", "paper_count"),
    )


class Follow(Base):
    """Usuário seguindo um autor, instituição ou tópico."""

    __tablename__ = "follows"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True
    )

    target_type: Mapped[str] = mapped_column(String(20), nullable=False)  # author | institution | topic
    target_id: Mapped[int] = mapped_column(Integer, nullable=False)

    __table_args__ = (
        UniqueConstraint(
            "user_id", "target_type", "target_id", name="uq_follows_user_target"
        ),
        Index("ix_follows_target", "target_type", "target_id"),
    )

# ============================================================
# Topics
# ============================================================
class Topic(Base):
    __tablename__ = "topics"

    id: Mapped[int] = mapped_column(primary_key=True)
    slug: Mapped[str] = mapped_column(String(100), unique=True, index=True)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    # Rastreamento do clustering
    cluster_id: Mapped[Optional[int]] = mapped_column(Integer, nullable=True, index=True)
    keywords: Mapped[list[str]] = mapped_column(ARRAY(String), default=list)
    paper_count: Mapped[int] = mapped_column(Integer, default=0)

    # Snapshot mais recente do run de clustering
    last_clustered_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, index=True)

    papers: Mapped[list["Paper"]] = relationship(
        secondary=paper_topics,
        back_populates="topics",
    )


# ============================================================
# ParsedContent (one per paper)
# ============================================================
class ParsedContent(Base):
    __tablename__ = "parsed_contents"

    id: Mapped[int] = mapped_column(primary_key=True)
    paper_id: Mapped[int] = mapped_column(
        ForeignKey("papers.id", ondelete="CASCADE"),
        unique=True,
        index=True,
    )

    parser: Mapped[str] = mapped_column(String(50), nullable=False)  # "llamaparse" | "nougat" | "docling"
    markdown: Mapped[str] = mapped_column(Text, nullable=False)
    figures: Mapped[list[dict]] = mapped_column(JSON, default=list)
    equations: Mapped[list[dict]] = mapped_column(JSON, default=list)
    parse_ms: Mapped[int] = mapped_column(Integer)

    paper: Mapped[Paper] = relationship(back_populates="parsed_content")


# ============================================================
# IngestionRun (observability)
# ============================================================
class IngestionRun(Base):
    __tablename__ = "ingestion_runs"

    id: Mapped[int] = mapped_column(primary_key=True)
    source: Mapped[str] = mapped_column(String(50), nullable=False, index=True)  # "arxiv" | "openalex" | ...
    status: Mapped[RunStatus] = mapped_column(SQLEnum(RunStatus, name="run_status"), nullable=False)

    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    finished_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)

    papers_found: Mapped[int] = mapped_column(Integer, default=0)
    papers_new: Mapped[int] = mapped_column(Integer, default=0)
    errors: Mapped[int] = mapped_column(Integer, default=0)

    log: Mapped[dict] = mapped_column(JSON, default=dict)


# ============================================================
# DecodedContent (many-to-1 with papers — one row per section per paper)
# ============================================================
class DecodedContent(Base):
    __tablename__ = "decoded_contents"

    id: Mapped[int] = mapped_column(primary_key=True)
    paper_id: Mapped[int] = mapped_column(
        ForeignKey("papers.id", ondelete="CASCADE"),
        index=True,
    )
    section: Mapped[str] = mapped_column(String(50), nullable=False)  # "one_sentence" | ...

    content: Mapped[dict] = mapped_column(JSON, nullable=False)
    schema_version: Mapped[int] = mapped_column(Integer, default=1)

    model: Mapped[str] = mapped_column(String(100), nullable=False)
    prompt_version: Mapped[str] = mapped_column(String(20), nullable=False)
    input_tokens: Mapped[int] = mapped_column(Integer, default=0)
    output_tokens: Mapped[int] = mapped_column(Integer, default=0)
    cost_usd: Mapped[float] = mapped_column(Float, default=0.0)
    latency_ms: Mapped[int] = mapped_column(Integer, default=0)

    __table_args__ = (
        UniqueConstraint(
            "paper_id",
            "section",
            "schema_version",
            "prompt_version",
            name="uq_decoded_contents_paper_section_versions",
        ),
        Index("ix_decoded_contents_section", "section"),
    )


# ============================================================
# Users
# ============================================================
class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True)
    clerk_user_id: Mapped[str] = mapped_column(String(100), unique=True, index=True)

    email: Mapped[Optional[str]] = mapped_column(String(320), nullable=True, index=True)
    display_name: Mapped[Optional[str]] = mapped_column(String(200), nullable=True)
    avatar_url: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    # Plano e créditos
    plan: Mapped[str] = mapped_column(String(20), default="free")  # free | pro
    credits_remaining: Mapped[int] = mapped_column(Integer, default=3)
    credits_reset_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    saved_papers: Mapped[list["SavedPaper"]] = relationship(
        back_populates="user",
        cascade="all, delete-orphan",
    )


class SavedPaper(Base):
    __tablename__ = "saved_papers"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    paper_id: Mapped[int] = mapped_column(
        ForeignKey("papers.id", ondelete="CASCADE"), index=True
    )

    note: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    user: Mapped[User] = relationship(back_populates="saved_papers")
    paper: Mapped["Paper"] = relationship()

    __table_args__ = (
        UniqueConstraint("user_id", "paper_id", name="uq_saved_papers_user_paper"),
    )


class ReadEvent(Base):
    """Registro de leitura — alimenta o digest personalizado na Semana 5."""

    __tablename__ = "read_events"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    paper_id: Mapped[int] = mapped_column(
        ForeignKey("papers.id", ondelete="CASCADE"), index=True
    )
    section: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)

    __table_args__ = (
        Index("ix_read_events_user_created", "user_id", "created_at"),
    )

# ============================================================
# ExplanationMode — geração sob demanda, cache permanente
# ============================================================
class ModeStatus(str, Enum):
    PENDING = "pending"
    GENERATING = "generating"
    READY = "ready"
    FAILED = "failed"
    NOT_APPLICABLE = "not_applicable"


class ExplanationMode(Base):
    __tablename__ = "explanation_modes"

    id: Mapped[int] = mapped_column(primary_key=True)
    paper_id: Mapped[int] = mapped_column(
        ForeignKey("papers.id", ondelete="CASCADE"),
        index=True,
    )
    mode: Mapped[str] = mapped_column(String(30), nullable=False)

    status: Mapped[ModeStatus] = mapped_column(
        SQLEnum(ModeStatus, name="mode_status"),
        default=ModeStatus.PENDING,
        index=True,
    )
    content: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)
    error: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    schema_version: Mapped[int] = mapped_column(Integer, default=1)
    prompt_version: Mapped[str] = mapped_column(String(20), nullable=False)

    model: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    input_tokens: Mapped[int] = mapped_column(Integer, default=0)
    output_tokens: Mapped[int] = mapped_column(Integer, default=0)
    cost_usd: Mapped[float] = mapped_column(Float, default=0.0)
    latency_ms: Mapped[int] = mapped_column(Integer, default=0)

    requested_by_user_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
    request_count: Mapped[int] = mapped_column(Integer, default=1)

    __table_args__ = (
        UniqueConstraint(
            "paper_id",
            "mode",
            "schema_version",
            "prompt_version",
            name="uq_explanation_modes_paper_mode_versions",
        ),
        Index("ix_explanation_modes_status", "status"),
    )


class CreditLedger(Base):
    """Registro de consumo de créditos. Append-only."""

    __tablename__ = "credit_ledger"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"),
        index=True,
    )
    delta: Mapped[int] = mapped_column(Integer, nullable=False)
    reason: Mapped[str] = mapped_column(String(50), nullable=False)
    paper_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("papers.id", ondelete="SET NULL"),
        nullable=True,
    )
    mode: Mapped[Optional[str]] = mapped_column(String(30), nullable=True)
    balance_after: Mapped[int] = mapped_column(Integer, nullable=False)

    __table_args__ = (
        Index("ix_credit_ledger_user_created", "user_id", "created_at"),
    )

class TopicSnapshot(Base):
    """
    Tamanho de um tópico numa janela de tempo.

    Uma linha por (tópico, semana). É isso que transforma "esse tópico
    existe" em "esse tópico cresceu 40% em três semanas".
    """

    __tablename__ = "topic_snapshots"

    id: Mapped[int] = mapped_column(primary_key=True)
    topic_id: Mapped[int] = mapped_column(
        ForeignKey("topics.id", ondelete="CASCADE"), index=True
    )

    window_start: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    window_end: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    paper_count: Mapped[int] = mapped_column(Integer, default=0)
    total_citations: Mapped[int] = mapped_column(Integer, default=0)
    mean_priority: Mapped[float] = mapped_column(Float, default=0.0)
    hn_mentions: Mapped[int] = mapped_column(Integer, default=0)

    __table_args__ = (
        UniqueConstraint(
            "topic_id", "window_start", name="uq_topic_snapshots_topic_window"
        ),
        Index("ix_topic_snapshots_window", "window_start"),
    )

class ClusteringRun(Base):
    """Auditoria de cada execução do clustering."""

    __tablename__ = "clustering_runs"

    id: Mapped[int] = mapped_column(primary_key=True)

    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    finished_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    papers_clustered: Mapped[int] = mapped_column(Integer, default=0)
    topics_found: Mapped[int] = mapped_column(Integer, default=0)
    outliers: Mapped[int] = mapped_column(Integer, default=0)

    min_cluster_size: Mapped[int] = mapped_column(Integer, default=5)
    naming_cost_usd: Mapped[float] = mapped_column(Float, default=0.0)

    log: Mapped[dict] = mapped_column(JSON, default=dict)


class DigestStatus(str, Enum):
    PENDING = "pending"
    SENT = "sent"
    FAILED = "failed"
    SKIPPED = "skipped"


class Digest(Base):
    """
    Um email de digest para um usuário numa semana.

    Guarda o conteúdo montado, não só o registro de envio. Isso permite
    reabrir o que foi enviado, depurar reclamações, e servir uma versão
    web do email.
    """

    __tablename__ = "digests"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True
    )

    week_start: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    status: Mapped[DigestStatus] = mapped_column(
        SQLEnum(DigestStatus, name="digest_status"),
        default=DigestStatus.PENDING,
        index=True,
    )

    # Conteúdo montado, na ordem de exibição
    content: Mapped[dict] = mapped_column(JSON, default=dict)
    paper_count: Mapped[int] = mapped_column(Integer, default=0)

    subject: Mapped[Optional[str]] = mapped_column(String(300), nullable=True)

    sent_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    provider_message_id: Mapped[Optional[str]] = mapped_column(
        String(200), nullable=True, index=True
    )
    error: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    # Engajamento — preenchido por webhook no Day 33
    opened_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    clicked_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    __table_args__ = (
        UniqueConstraint("user_id", "week_start", name="uq_digests_user_week"),
        Index("ix_digests_status_week", "status", "week_start"),
    )


class DigestPreference(Base):
    """Preferências de digest por usuário."""

    __tablename__ = "digest_preferences"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), unique=True, index=True
    )

    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    max_papers: Mapped[int] = mapped_column(Integer, default=6)

    # Se não segue nada, cai no feed geral por prioridade
    include_general: Mapped[bool] = mapped_column(Boolean, default=True)

    # Token opaco para o link de descadastro — não expõe o user_id
    unsubscribe_token: Mapped[str] = mapped_column(
        String(64), unique=True, index=True, nullable=False
    )


class PodcastStatus(str, Enum):
    PENDING = "pending"
    SCRIPTED = "scripted"
    GENERATING_AUDIO = "generating_audio"
    READY = "ready"
    FAILED = "failed"


class Podcast(Base):
    """Episódio de podcast de um paper."""

    __tablename__ = "podcasts"

    id: Mapped[int] = mapped_column(primary_key=True)
    paper_id: Mapped[int] = mapped_column(
        ForeignKey("papers.id", ondelete="CASCADE"),
        index=True,
    )

    status: Mapped[PodcastStatus] = mapped_column(
        SQLEnum(PodcastStatus, name="podcast_status"),
        default=PodcastStatus.PENDING,
        index=True,
    )

    # Roteiro
    script: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)
    script_model: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    script_cost_usd: Mapped[float] = mapped_column(Float, default=0.0)

    # Áudio
    audio_url: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    audio_bytes: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    duration_seconds: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    voice_id: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    audio_cost_usd: Mapped[float] = mapped_column(Float, default=0.0)

    # Capítulos com timestamp real, preenchidos depois do áudio
    chapters: Mapped[list[dict]] = mapped_column(JSON, default=list)

    schema_version: Mapped[int] = mapped_column(Integer, default=1)
    prompt_version: Mapped[str] = mapped_column(String(20), nullable=False)

    error: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    play_count: Mapped[int] = mapped_column(Integer, default=0)

    __table_args__ = (
        UniqueConstraint(
            "paper_id",
            "schema_version",
            "prompt_version",
            name="uq_podcasts_paper_versions",
        ),
        Index("ix_podcasts_status", "status"),
    )