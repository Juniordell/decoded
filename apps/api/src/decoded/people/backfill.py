"""Popula authors e institutions a partir dos dados já enriquecidos.

O enricher guarda authorships da OpenAlex em papers.extra['openalex'].
Esse dado tem openalex_id por autor e por instituição — a base para
desambiguação confiável.
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass, field

import structlog
from sqlalchemy import delete, func, select, update
from sqlalchemy.dialects.postgresql import insert

from decoded.db.base import async_session_factory
from decoded.db.models import Author, Institution, Paper, paper_authors

logger = structlog.get_logger()


def normalize_name(name: str) -> str:
    """
    Forma canônica para agrupar quando não há openalex_id.

    'José P. da Silva' e 'Jose P Da Silva' colapsam no mesmo valor.
    """
    n = unicodedata.normalize("NFKD", name)
    n = "".join(c for c in n if not unicodedata.combining(c))
    n = re.sub(r"[^\w\s]", " ", n.lower())
    return " ".join(n.split())


def slugify(text: str, suffix: str | None = None) -> str:
    s = unicodedata.normalize("NFKD", text)
    s = "".join(c for c in s if not unicodedata.combining(c))
    s = re.sub(r"[^a-z0-9\s-]", "", s.lower())
    s = re.sub(r"[\s_]+", "-", s.strip())[:140]
    return f"{s}-{suffix}" if suffix else s


@dataclass
class ParsedAuthorship:
    name: str
    openalex_id: str | None
    affiliation: str | None
    institution_openalex_id: str | None
    position: int


@dataclass
class BackfillStats:
    papers_processed: int = 0
    authors_created: int = 0
    institutions_created: int = 0
    links_created: int = 0
    skipped_no_data: int = 0
    disambiguated: int = 0
    name_matched: int = 0
    errors: list[str] = field(default_factory=list)


def _parse_authorships(paper: Paper) -> list[ParsedAuthorship]:
    """
    Extrai autores. Prefere OpenAlex; cai para a lista bruta do arXiv.
    """
    extra = paper.extra or {}
    oa = extra.get("openalex") or {}
    authorships = oa.get("authorships") or []

    if authorships:
        out: list[ParsedAuthorship] = []
        for i, a in enumerate(authorships):
            name = (a.get("name") or "").strip()
            if not name:
                continue
            out.append(
                ParsedAuthorship(
                    name=name,
                    openalex_id=a.get("openalex_id"),
                    affiliation=a.get("affiliation"),
                    institution_openalex_id=a.get("institution_openalex_id"),
                    position=i,
                )
            )
        if out:
            return out

    # Fallback: nomes crus do arXiv, sem afiliação nem id
    raw = extra.get("authors_raw") or []
    return [
        ParsedAuthorship(
            name=n.strip(),
            openalex_id=None,
            affiliation=None,
            institution_openalex_id=None,
            position=i,
        )
        for i, n in enumerate(raw)
        if n and n.strip()
    ]


async def backfill_people(limit: int | None = None) -> dict:
    """
    Reconstrói authors, institutions e paper_authors do zero.

    Reconstrói em vez de incremental porque a desambiguação melhora
    conforme mais papers chegam — um autor sem openalex_id hoje pode
    ganhar um amanhã, e a fusão precisa acontecer globalmente.
    """
    stats = BackfillStats()
    log = logger.bind(source="people_backfill")
    log.info("backfill.start")

    async with async_session_factory() as session:
        # Limpa vínculos. Authors e institutions são reaproveitados por chave.
        await session.execute(delete(paper_authors))
        await session.commit()

        stmt = select(Paper).order_by(Paper.published_at.desc())
        if limit:
            stmt = stmt.limit(limit)
        papers = list((await session.execute(stmt)).scalars().all())

        log.info("backfill.papers_loaded", count=len(papers))

        # Caches em memória — evitam ida ao banco por autor repetido
        author_by_oa: dict[str, int] = {}
        author_by_name: dict[str, int] = {}
        institution_by_oa: dict[str, int] = {}
        institution_by_name: dict[str, int] = {}
        used_slugs: set[str] = set()

        # Carrega o que já existe
        for a in (await session.execute(select(Author))).scalars().all():
            if a.openalex_id:
                author_by_oa[a.openalex_id] = a.id
            author_by_name.setdefault(a.normalized_name, a.id)
            used_slugs.add(a.slug)

        for inst in (await session.execute(select(Institution))).scalars().all():
            if inst.openalex_id:
                institution_by_oa[inst.openalex_id] = inst.id
            institution_by_name.setdefault(normalize_name(inst.name), inst.id)
            used_slugs.add(inst.slug)

        def unique_slug(base: str) -> str:
            slug = base
            n = 2
            while slug in used_slugs:
                slug = f"{base}-{n}"
                n += 1
            used_slugs.add(slug)
            return slug

        async def get_or_create_institution(
            name: str, openalex_id: str | None
        ) -> int | None:
            if not name:
                return None

            if openalex_id and openalex_id in institution_by_oa:
                return institution_by_oa[openalex_id]

            norm = normalize_name(name)
            if not openalex_id and norm in institution_by_name:
                return institution_by_name[norm]

            slug = unique_slug(slugify(name))
            inst = Institution(
                openalex_id=openalex_id,
                slug=slug,
                name=name[:400],
            )
            session.add(inst)
            await session.flush()

            if openalex_id:
                institution_by_oa[openalex_id] = inst.id
            institution_by_name[norm] = inst.id
            stats.institutions_created += 1
            return inst.id

        async def get_or_create_author(pa: ParsedAuthorship) -> int:
            norm = normalize_name(pa.name)

            # Caminho confiável
            if pa.openalex_id:
                if pa.openalex_id in author_by_oa:
                    return author_by_oa[pa.openalex_id]

                inst_id = await get_or_create_institution(
                    pa.affiliation or "", pa.institution_openalex_id
                )
                slug = unique_slug(slugify(pa.name))
                author = Author(
                    openalex_id=pa.openalex_id,
                    normalized_name=norm,
                    slug=slug,
                    name=pa.name[:300],
                    affiliation=pa.affiliation,
                    institution_id=inst_id,
                    is_disambiguated=True,
                )
                session.add(author)
                await session.flush()
                author_by_oa[pa.openalex_id] = author.id
                author_by_name.setdefault(norm, author.id)
                stats.authors_created += 1
                stats.disambiguated += 1
                return author.id

            # Fallback por nome
            if norm in author_by_name:
                stats.name_matched += 1
                return author_by_name[norm]

            slug = unique_slug(slugify(pa.name))
            author = Author(
                openalex_id=None,
                normalized_name=norm,
                slug=slug,
                name=pa.name[:300],
                affiliation=pa.affiliation,
                is_disambiguated=False,
            )
            session.add(author)
            await session.flush()
            author_by_name[norm] = author.id
            stats.authors_created += 1
            return author.id

        # --- Loop principal ---
        links: list[dict] = []

        for paper in papers:
            authorships = _parse_authorships(paper)
            if not authorships:
                stats.skipped_no_data += 1
                continue

            seen_in_paper: set[int] = set()

            for pa in authorships[:60]:  # papers com 100+ autores existem
                try:
                    author_id = await get_or_create_author(pa)
                    if author_id in seen_in_paper:
                        continue
                    seen_in_paper.add(author_id)
                    links.append(
                        {
                            "paper_id": paper.id,
                            "author_id": author_id,
                            "position": pa.position,
                        }
                    )
                except Exception as e:
                    stats.errors.append(f"{paper.arxiv_id}/{pa.name}: {e}")

            stats.papers_processed += 1

            if stats.papers_processed % 100 == 0:
                await session.commit()
                log.info("backfill.progress", papers=stats.papers_processed)

        await session.commit()

        # Insere vínculos em lotes
        BATCH = 500
        for i in range(0, len(links), BATCH):
            chunk = links[i : i + BATCH]
            await session.execute(
                insert(paper_authors).on_conflict_do_nothing(), chunk
            )
        stats.links_created = len(links)
        await session.commit()

        # --- Agregados ---
        log.info("backfill.computing_aggregates")

        await session.execute(
            update(Author).values(
                paper_count=(
                    select(func.count(paper_authors.c.paper_id))
                    .where(paper_authors.c.author_id == Author.id)
                    .scalar_subquery()
                ),
                total_citations=(
                    select(func.coalesce(func.sum(Paper.citation_count), 0))
                    .select_from(paper_authors)
                    .join(Paper, Paper.id == paper_authors.c.paper_id)
                    .where(paper_authors.c.author_id == Author.id)
                    .scalar_subquery()
                ),
            )
        )

        await session.execute(
            update(Institution).values(
                author_count=(
                    select(func.count(Author.id))
                    .where(Author.institution_id == Institution.id)
                    .scalar_subquery()
                ),
                paper_count=(
                    select(func.count(func.distinct(paper_authors.c.paper_id)))
                    .select_from(paper_authors)
                    .join(Author, Author.id == paper_authors.c.author_id)
                    .where(Author.institution_id == Institution.id)
                    .scalar_subquery()
                ),
                total_citations=(
                    select(func.coalesce(func.sum(Paper.citation_count), 0))
                    .select_from(paper_authors)
                    .join(Author, Author.id == paper_authors.c.author_id)
                    .join(Paper, Paper.id == paper_authors.c.paper_id)
                    .where(Author.institution_id == Institution.id)
                    .scalar_subquery()
                ),
            )
        )

        await session.commit()

    log.info(
        "backfill.done",
        papers=stats.papers_processed,
        authors=stats.authors_created,
        institutions=stats.institutions_created,
        links=stats.links_created,
        disambiguated=stats.disambiguated,
        name_matched=stats.name_matched,
        errors=len(stats.errors),
    )

    return {
        "papers_processed": stats.papers_processed,
        "authors_created": stats.authors_created,
        "institutions_created": stats.institutions_created,
        "links_created": stats.links_created,
        "disambiguated": stats.disambiguated,
        "name_matched": stats.name_matched,
        "skipped_no_data": stats.skipped_no_data,
        "errors": stats.errors[:10],
    }