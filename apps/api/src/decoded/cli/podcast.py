"""CLI do podcast.

Uso:
    poetry run python -m decoded.cli.podcast script --arxiv-id 2608.06221
    poetry run python -m decoded.cli.podcast show --arxiv-id 2608.06221
    poetry run python -m decoded.cli.podcast list
"""

import argparse
import asyncio
import sys

import structlog
from sqlalchemy import select

from decoded.config import settings
from decoded.db.base import async_session_factory
from decoded.db.models import Paper, Podcast
from decoded.logging import configure_logging
from decoded.observability.tracing import flush as flush_tracing
from decoded.observability.tracing import init_tracing
from decoded.podcast.pipeline import generate_script
from decoded.podcast.pipeline import generate_audio

logger = structlog.get_logger()


async def cmd_script(arxiv_id: str, force: bool) -> int:
    if not settings.anthropic_api_key:
        print("ANTHROPIC_API_KEY não definida")
        return 1

    init_tracing()
    try:
        result = await generate_script(
            arxiv_id=arxiv_id,
            anthropic_api_key=settings.anthropic_api_key,
            model=settings.podcast_script_model,
            force=force,
        )
    finally:
        flush_tracing()

    print("\n" + "=" * 68)
    for k, v in result.items():
        print(f"  {k:22} {v}")
    print("=" * 68 + "\n")
    return 0 if "error" not in result else 1


async def cmd_show(arxiv_id: str) -> int:
    """Imprime o roteiro para leitura em voz alta — o teste que importa."""
    async with async_session_factory() as session:
        row = (
            await session.execute(
                select(Podcast, Paper.title)
                .join(Paper, Paper.id == Podcast.paper_id)
                .where(Paper.arxiv_id == arxiv_id)
            )
        ).one_or_none()

    if row is None:
        print(f"Nenhum roteiro para {arxiv_id}")
        return 1

    podcast, title = row
    script = podcast.script or {}

    print("\n" + "=" * 72)
    print(f"  {title[:66]}")
    print(f"  ~{script.get('estimated_seconds', 0) // 60}m{script.get('estimated_seconds', 0) % 60:02d}s")
    print("=" * 72)

    print(f"\n{script.get('intro', '')}\n")

    for i, chapter in enumerate(script.get("chapters", []), 1):
        print("-" * 72)
        print(f"  {i}. {chapter.get('title', '')}")
        print("-" * 72)
        print(f"\n{chapter.get('body', '')}\n")

    print("-" * 72)
    print(f"\n{script.get('outro', '')}\n")
    return 0


async def cmd_list() -> int:
    async with async_session_factory() as session:
        rows = (
            await session.execute(
                select(Podcast, Paper.arxiv_id, Paper.title)
                .join(Paper, Paper.id == Podcast.paper_id)
                .order_by(Podcast.id.desc())
                .limit(30)
            )
        ).all()

    if not rows:
        print("\nNenhum podcast ainda.\n")
        return 0

    print("\n" + "=" * 88)
    print(f"  {'ARXIV':<14} {'STATUS':<18} {'DUR':>6}  TITLE")
    print("=" * 88)
    for podcast, arxiv_id, title in rows:
        secs = podcast.duration_seconds or (podcast.script or {}).get(
            "estimated_seconds", 0
        )
        dur = f"{secs // 60}:{secs % 60:02d}" if secs else "—"
        print(
            f"  {arxiv_id:<14} {podcast.status.value:<18} {dur:>6}  {title[:44]}"
        )
    print()
    return 0


async def cmd_audio(arxiv_id: str, force: bool) -> int:
    missing = [
        name
        for name, value in [
            ("ELEVENLABS_API_KEY", settings.elevenlabs_api_key),
            ("ELEVENLABS_VOICE_ID", settings.elevenlabs_voice_id),
            ("R2_ACCOUNT_ID", settings.r2_account_id),
            ("R2_ACCESS_KEY_ID", settings.r2_access_key_id),
            ("R2_SECRET_ACCESS_KEY", settings.r2_secret_access_key),
        ]
        if not value
    ]
    if missing:
        print(f"Faltando: {', '.join(missing)}")
        return 1

    init_tracing()
    try:
        result = await generate_audio(
            arxiv_id=arxiv_id,
            elevenlabs_api_key=settings.elevenlabs_api_key,
            voice_id=settings.elevenlabs_voice_id,
            tts_model=settings.elevenlabs_model,
            r2_account_id=settings.r2_account_id,
            r2_access_key_id=settings.r2_access_key_id,
            r2_secret_access_key=settings.r2_secret_access_key,
            r2_bucket=settings.r2_bucket,
            r2_public_url=settings.r2_public_url,
            daily_budget_usd=settings.podcast_daily_budget_usd,
            force=force,
        )
    finally:
        flush_tracing()

    print("\n" + "=" * 68)
    for k, v in result.items():
        print(f"  {k:22} {v}")
    print("=" * 68 + "\n")
    return 0 if "error" not in result else 1


async def cmd_full(arxiv_id: str, force: bool) -> int:
    """Roteiro e áudio numa tacada."""
    rc = await cmd_script(arxiv_id, force)
    if rc != 0:
        return rc
    return await cmd_audio(arxiv_id, force)


async def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("command", choices=["script", "audio", "full", "show", "list"])
    parser.add_argument("--arxiv-id")
    parser.add_argument("--force", action="store_true")
    
    args = parser.parse_args()

    configure_logging("INFO")

    if args.command == "list":
        return await cmd_list()

    if not args.arxiv_id:
        print("--arxiv-id é obrigatório")
        return 1

    if args.command == "script":
        return await cmd_script(args.arxiv_id, args.force)

    if args.command == "audio":
        return await cmd_audio(args.arxiv_id, args.force)

    if args.command == "full":
        return await cmd_full(args.arxiv_id, args.force)

    return await cmd_show(args.arxiv_id)


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))