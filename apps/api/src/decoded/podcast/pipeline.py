from __future__ import annotations

import structlog
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert

from decoded.db.base import async_session_factory
from decoded.db.models import Paper, Podcast, PodcastStatus
from decoded.db.repositories.decoded_contents import DecodedContentsRepository
from decoded.decoding.pipeline import _flatten_deep_dive
from decoded.decoding.prompts import VERSION as DECODE_VERSION
from decoded.observability.tracing import trace_span
from decoded.podcast.prompts import PODCAST_PROMPT_VERSION
from decoded.podcast.schemas import PODCAST_SCHEMA_VERSION
from decoded.podcast.script import ScriptWriter

logger = structlog.get_logger()


async def generate_script(
    arxiv_id: str,
    anthropic_api_key: str,
    model: str,
    force: bool = False,
) -> dict:
    """
    Gera o roteiro de um paper.

    Exige que o paper já esteja decodificado — o roteiro é montado a
    partir do deep dive, não do PDF bruto.
    """
    log = logger.bind(arxiv_id=arxiv_id)

    with trace_span(
        "podcast_script",
        input={"arxiv_id": arxiv_id},
        tags=["podcast", "script"],
    ) as span:
        async with async_session_factory() as session:
            paper = (
                await session.execute(
                    select(Paper).where(Paper.arxiv_id == arxiv_id)
                )
            ).scalar_one_or_none()

            if paper is None:
                return {"error": "paper_not_found"}

            existing = (
                await session.execute(
                    select(Podcast).where(
                        Podcast.paper_id == paper.id,
                        Podcast.schema_version == PODCAST_SCHEMA_VERSION,
                        Podcast.prompt_version == PODCAST_PROMPT_VERSION,
                    )
                )
            ).scalar_one_or_none()

            if existing is not None and not force:
                if existing.status in (
                    PodcastStatus.SCRIPTED,
                    PodcastStatus.READY,
                    PodcastStatus.GENERATING_AUDIO,
                ):
                    log.info("script.cache_hit", status=existing.status.value)
                    return {
                        "status": existing.status.value,
                        "cached": True,
                        "podcast_id": existing.id,
                        "estimated_seconds": (existing.script or {}).get(
                            "estimated_seconds", 0
                        ),
                    }

            # Material de origem
            decoded_repo = DecodedContentsRepository(session)
            sections = await decoded_repo.get_all_sections(
                paper_id=paper.id, prompt_version=DECODE_VERSION
            )

            deep_dive_row = sections.get("deep_dive")
            if deep_dive_row is None:
                log.warning("script.no_deep_dive")
                return {"error": "no_deep_dive", "hint": "decode the paper first"}

            deep_dive_text = _flatten_deep_dive(deep_dive_row.content)

            one_sentence = None
            if os_row := sections.get("one_sentence"):
                one_sentence = (os_row.content or {}).get("text")

            sixty_second = None
            if ss_row := sections.get("sixty_second"):
                sixty_second = ss_row.content

            analogies = None
            if an_row := sections.get("analogies"):
                analogies = (an_row.content or {}).get("items", [])

            # Geração
            try:
                async with ScriptWriter(anthropic_api_key, model) as writer:
                    script = await writer.write(
                        title=paper.title,
                        one_sentence=one_sentence,
                        sixty_second=sixty_second,
                        deep_dive_text=deep_dive_text,
                        analogies=analogies,
                    )
                    cost = writer.total_cost

            except Exception as e:
                log.error("script.failed", error=str(e))
                await session.execute(
                    insert(Podcast)
                    .values(
                        paper_id=paper.id,
                        status=PodcastStatus.FAILED,
                        schema_version=PODCAST_SCHEMA_VERSION,
                        prompt_version=PODCAST_PROMPT_VERSION,
                        error=str(e)[:2000],
                    )
                    .on_conflict_do_update(
                        constraint="uq_podcasts_paper_versions",
                        set_={"status": PodcastStatus.FAILED, "error": str(e)[:2000]},
                    )
                )
                await session.commit()
                return {"error": str(e)}

            # Persistência
            stmt = (
                insert(Podcast)
                .values(
                    paper_id=paper.id,
                    status=PodcastStatus.SCRIPTED,
                    script=script.model_dump(),
                    script_model=model,
                    script_cost_usd=cost,
                    schema_version=PODCAST_SCHEMA_VERSION,
                    prompt_version=PODCAST_PROMPT_VERSION,
                    error=None,
                )
                .on_conflict_do_update(
                    constraint="uq_podcasts_paper_versions",
                    set_={
                        "status": PodcastStatus.SCRIPTED,
                        "script": script.model_dump(),
                        "script_model": model,
                        "script_cost_usd": cost,
                        "error": None,
                    },
                )
                .returning(Podcast.id)
            )
            podcast_id = (await session.execute(stmt)).scalar_one()
            await session.commit()

        span.update(
            output={"chapters": len(script.chapters)},
            metadata={
                "estimated_seconds": script.estimated_seconds,
                "cost_usd": cost,
            },
        )

    log.info(
        "script.done",
        podcast_id=podcast_id,
        chapters=len(script.chapters),
        estimated_seconds=script.estimated_seconds,
        cost_usd=round(cost, 6),
    )

    return {
        "status": "scripted",
        "cached": False,
        "podcast_id": podcast_id,
        "chapters": len(script.chapters),
        "chars": len(script.full_text),
        "estimated_seconds": script.estimated_seconds,
        "cost_usd": round(cost, 6),
    }