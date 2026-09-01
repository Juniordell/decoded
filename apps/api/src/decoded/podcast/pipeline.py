from __future__ import annotations

from datetime import datetime, timedelta, timezone

import structlog
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy import func

from decoded.db.base import async_session_factory
from decoded.db.models import Paper, Podcast, PodcastStatus
from decoded.db.repositories.decoded_contents import DecodedContentsRepository
from decoded.decoding.pipeline import _flatten_deep_dive
from decoded.decoding.prompts import VERSION as DECODE_VERSION
from decoded.observability.tracing import trace_span
from decoded.podcast.prompts import PODCAST_PROMPT_VERSION
from decoded.podcast.schemas import PODCAST_SCHEMA_VERSION
from decoded.podcast.script import ScriptWriter
from decoded.db.models import Podcast, PodcastStatus
from decoded.podcast.timing import compute_chapters, read_duration_seconds
from decoded.podcast.tts import ElevenLabsClient
from decoded.storage.r2 import R2Client

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

async def _spent_on_audio_today() -> float:
    """Gasto com TTS nas últimas 24h."""
    cutoff = datetime.now(timezone.utc) - timedelta(days=1)
    async with async_session_factory() as session:
        return (
            await session.execute(
                select(func.coalesce(func.sum(Podcast.audio_cost_usd), 0.0)).where(
                    Podcast.updated_at >= cutoff
                )
            )
        ).scalar_one() or 0.0


async def generate_audio(
    arxiv_id: str,
    elevenlabs_api_key: str,
    voice_id: str,
    tts_model: str,
    r2_account_id: str,
    r2_access_key_id: str,
    r2_secret_access_key: str,
    r2_bucket: str,
    r2_public_url: str | None,
    daily_budget_usd: float = 3.0,
    force: bool = False,
) -> dict:
    """
    Sintetiza e publica o áudio de um roteiro existente.

    O teto de gasto é verificado antes de chamar o TTS — depois da
    chamada você já pagou pelos caracteres.
    """
    log = logger.bind(arxiv_id=arxiv_id)

    with trace_span(
        "podcast_audio",
        input={"arxiv_id": arxiv_id},
        tags=["podcast", "audio"],
    ) as span:
        # --- Carrega ---
        async with async_session_factory() as session:
            row = (
                await session.execute(
                    select(Podcast, Paper.title)
                    .join(Paper, Paper.id == Podcast.paper_id)
                    .where(
                        Paper.arxiv_id == arxiv_id,
                        Podcast.schema_version == PODCAST_SCHEMA_VERSION,
                        Podcast.prompt_version == PODCAST_PROMPT_VERSION,
                    )
                )
            ).one_or_none()

        if row is None:
            return {"error": "no_script", "hint": "generate the script first"}

        podcast, title = row

        if podcast.status == PodcastStatus.READY and not force:
            log.info("audio.cache_hit")
            return {
                "status": "ready",
                "cached": True,
                "audio_url": podcast.audio_url,
                "duration_seconds": podcast.duration_seconds,
            }

        if not podcast.script:
            return {"error": "script_empty"}

        # --- Orçamento ---
        spent = await _spent_on_audio_today()
        if spent >= daily_budget_usd:
            log.warning("audio.budget_exhausted", spent=round(spent, 4))
            return {"error": "daily_budget_exhausted", "spent_today": round(spent, 4)}

        script_chars = len(
            podcast.script.get("intro", "")
            + "".join(c.get("body", "") for c in podcast.script.get("chapters", []))
            + podcast.script.get("outro", "")
        )
        estimated_cost = script_chars * (5.0 / 30_000)

        if spent + estimated_cost > daily_budget_usd:
            log.warning(
                "audio.would_exceed_budget",
                spent=round(spent, 4),
                estimated=round(estimated_cost, 4),
            )
            return {"error": "would_exceed_budget", "estimated_cost": round(estimated_cost, 4)}

        # --- Marca em progresso ---
        async with async_session_factory() as session:
            p = (
                await session.execute(select(Podcast).where(Podcast.id == podcast.id))
            ).scalar_one()
            p.status = PodcastStatus.GENERATING_AUDIO
            await session.commit()

        try:
            # --- Síntese ---
            tts = ElevenLabsClient(
                api_key=elevenlabs_api_key,
                voice_id=voice_id,
                model=tts_model,
            )
            synthesis = await tts.synthesize_script(podcast.script)
            audio_bytes = synthesis.combined_audio

            if not audio_bytes:
                raise RuntimeError("TTS retornou áudio vazio")

            # --- Duração e capítulos ---
            # Soma dos segmentos é confiável; ler o arquivo concatenado não é,
            # porque o mutagen lê só o primeiro header
            duration = synthesis.total_duration_seconds
            if duration <= 0:
                duration = read_duration_seconds(audio_bytes) or podcast.script.get(
                    "estimated_seconds", 0
                )

            chapters = compute_chapters(podcast.script, duration)

            # --- Upload ---
            r2 = R2Client(
                account_id=r2_account_id,
                access_key_id=r2_access_key_id,
                secret_access_key=r2_secret_access_key,
                bucket=r2_bucket,
                public_url=r2_public_url,
            )

            # A versão do prompt na chave permite regenerar sem invalidar cache
            key = f"podcasts/{arxiv_id}/{PODCAST_PROMPT_VERSION}.mp3"
            upload = await r2.upload(
                key=key,
                data=audio_bytes,
                content_type="audio/mpeg",
            )

            # --- Persiste ---
            async with async_session_factory() as session:
                p = (
                    await session.execute(
                        select(Podcast).where(Podcast.id == podcast.id)
                    )
                ).scalar_one()
                p.status = PodcastStatus.READY
                p.audio_url = upload.url
                p.audio_bytes = upload.size_bytes
                p.duration_seconds = duration
                p.voice_id = voice_id
                p.audio_cost_usd = synthesis.cost_usd
                p.chapters = chapters
                p.error = None
                await session.commit()

        except Exception as e:
            log.error("audio.failed", error=str(e))
            async with async_session_factory() as session:
                p = (
                    await session.execute(
                        select(Podcast).where(Podcast.id == podcast.id)
                    )
                ).scalar_one()
                p.status = PodcastStatus.FAILED
                p.error = str(e)[:2000]
                await session.commit()
            return {"error": str(e)}

        span.update(
            output={"duration_seconds": duration, "chapters": len(chapters)},
            metadata={"cost_usd": synthesis.cost_usd, "chars": synthesis.total_chars},
        )

    log.info(
        "audio.done",
        duration_seconds=duration,
        size_kb=upload.size_bytes // 1024,
        cost_usd=round(synthesis.cost_usd, 4),
    )

    return {
        "status": "ready",
        "cached": False,
        "audio_url": upload.url,
        "duration_seconds": duration,
        "size_bytes": upload.size_bytes,
        "chapters": len(chapters),
        "chars": synthesis.total_chars,
        "cost_usd": round(synthesis.cost_usd, 4),
    }