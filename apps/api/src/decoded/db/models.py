from datetime import datetime
from enum import Enum
from typing import Optional

from sqlalchemy import (
    ARRAY,
    JSON,
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
    openalex_id: Mapped[Optional[str]] = mapped_column(String(100), unique=True, nullable=True)
    name: Mapped[str] = mapped_column(String(300), nullable=False, index=True)
    affiliation: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    h_index: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)

    papers: Mapped[list[Paper]] = relationship(
        secondary=paper_authors,
        back_populates="authors",
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

    papers: Mapped[list[Paper]] = relationship(
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