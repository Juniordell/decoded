"""CLI do digest.

Uso:
    poetry run python -m decoded.cli.digest build --user-id 1
    poetry run python -m decoded.cli.digest build-all
    poetry run python -m decoded.cli.digest preview --user-id 1 --out /tmp/digest.html
    poetry run python -m decoded.cli.digest list
"""

import argparse
import asyncio
import sys
from datetime import datetime, timedelta, timezone

import structlog
from sqlalchemy import select

from decoded.config import settings
from decoded.db.base import async_session_factory
from decoded.db.models import Digest, User
from decoded.digest.builder import build_all, build_for_user, week_start
from decoded.digest.template import render_html, render_text
from decoded.logging import configure_logging
from decoded.digest.sender import send_one, send_pending

logger = structlog.get_logger()


async def cmd_build(user_id: int, force: bool, weeks_ago: int) -> int:
    target = datetime.now(timezone.utc) - timedelta(weeks=weeks_ago)
    result = await build_for_user(
        user_id=user_id,
        target_week=target,
        anthropic_api_key=settings.anthropic_api_key,
        subject_model=settings.digest_subject_model,
        force=force,
    )

    print("\n" + "=" * 68)
    for k, v in result.items():
        print(f"  {k:20} {v}")
    print("=" * 68 + "\n")
    return 0 if "error" not in result else 1


async def cmd_build_all(force: bool, weeks_ago: int) -> int:
    target = datetime.now(timezone.utc) - timedelta(weeks=weeks_ago)
    result = await build_all(
        target_week=target,
        anthropic_api_key=settings.anthropic_api_key,
        subject_model=settings.digest_subject_model,
        force=force,
    )

    print("\n" + "=" * 68)
    for k, v in result.items():
        print(f"  {k:20} {v}")
    print("=" * 68 + "\n")
    return 0


async def cmd_preview(user_id: int, out_path: str, weeks_ago: int) -> int:
    """Renderiza o digest mais recente em arquivo, para inspeção visual."""
    target_week = week_start(datetime.now(timezone.utc) - timedelta(weeks=weeks_ago))

    async with async_session_factory() as session:
        digest = (
            await session.execute(
                select(Digest)
                .where(Digest.user_id == user_id, Digest.week_start == target_week)
            )
        ).scalar_one_or_none()

    if digest is None:
        print(f"Nenhum digest para user {user_id} na semana de {target_week.date()}")
        print("Rode: poetry run python -m decoded.cli.digest build --user-id N")
        return 1

    html_out = render_html(
        subject=digest.subject or "Decoded",
        content=digest.content,
        site_url=settings.site_url,
        week_start=digest.week_start,
    )
    text_out = render_text(
        subject=digest.subject or "Decoded",
        content=digest.content,
        site_url=settings.site_url,
        week_start=digest.week_start,
    )

    with open(out_path, "w", encoding="utf-8") as f:
        f.write(html_out)

    txt_path = out_path.rsplit(".", 1)[0] + ".txt"
    with open(txt_path, "w", encoding="utf-8") as f:
        f.write(text_out)

    print("\n" + "=" * 68)
    print(f"  ASSUNTO   {digest.subject}")
    print(f"  PREVIEW   {digest.content.get('preview', '')}")
    print(f"  PAPERS    {digest.paper_count}")
    print("=" * 68)
    print(f"\n  html  {out_path}")
    print(f"  text  {txt_path}\n")
    return 0


async def cmd_list() -> int:
    async with async_session_factory() as session:
        rows = (
            await session.execute(
                select(Digest, User.email)
                .join(User, User.id == Digest.user_id)
                .order_by(Digest.week_start.desc(), Digest.id.desc())
                .limit(30)
            )
        ).all()

    if not rows:
        print("\nNenhum digest construído ainda.\n")
        return 0

    print("\n" + "=" * 88)
    print(f"  {'WEEK':<12} {'STATUS':<10} {'N':>3}  {'EMAIL':<26} SUBJECT")
    print("=" * 88)
    for digest, email in rows:
        print(
            f"  {digest.week_start.date().isoformat():<12} "
            f"{digest.status.value:<10} {digest.paper_count:>3}  "
            f"{(email or '—')[:26]:<26} {(digest.subject or '')[:34]}"
        )
    print()
    return 0


async def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "command",
        choices=["build", "build-all", "preview", "list", "send", "test"],
    )
    parser.add_argument("--limit", type=int, default=None)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--digest-id", type=int)
    parser.add_argument("--to", help="Email de teste, sem marcar como enviado")
    parser.add_argument("--user-id", type=int)
    parser.add_argument("--force", action="store_true")
    parser.add_argument(
        "--weeks-ago",
        type=int,
        default=1,
        help="Qual semana montar. 1 = semana passada.",
    )
    parser.add_argument("--out", default="/tmp/digest.html")
    args = parser.parse_args()

    configure_logging("INFO")

    if args.command == "build":
        if not args.user_id:
            print("--user-id é obrigatório")
            return 1
        return await cmd_build(args.user_id, args.force, args.weeks_ago)

    if args.command == "build-all":
        return await cmd_build_all(args.force, args.weeks_ago)

    if args.command == "preview":
        if not args.user_id:
            print("--user-id é obrigatório")
            return 1
        return await cmd_preview(args.user_id, args.out, args.weeks_ago)

    if args.command == "list":
        return await cmd_list()

    if args.command == "send":
        return await cmd_send(args.weeks_ago, args.limit, args.dry_run)

    if args.command == "test":
        if not args.digest_id or not args.to:
            print("--digest-id e --to são obrigatórios")
            return 1
        return await cmd_test(args.digest_id, args.to)

    return 1


async def cmd_send(
    weeks_ago: int,
    limit: int | None,
    dry_run: bool,
) -> int:
    if not settings.resend_api_key and not dry_run:
        print("RESEND_API_KEY não definida")
        return 1

    target = datetime.now(timezone.utc) - timedelta(weeks=weeks_ago)

    result = await send_pending(
        api_key=settings.resend_api_key or "",
        from_email=settings.digest_from_email,
        site_url=settings.site_url,
        reply_to=settings.digest_reply_to,
        target_week=target,
        limit=limit,
        daily_cap=settings.digest_daily_cap,
        rate_per_second=settings.digest_send_rate_per_second,
        dry_run=dry_run,
    )

    print("\n" + "=" * 68)
    for k, v in result.items():
        if k == "errors" and v:
            print(f"  {k}:")
            for e in v:
                print(f"    {e}")
        else:
            print(f"  {k:20} {v}")
    print("=" * 68 + "\n")
    return 0


async def cmd_test(digest_id: int, to: str) -> int:
    if not settings.resend_api_key:
        print("RESEND_API_KEY não definida")
        return 1

    result = await send_one(
        digest_id=digest_id,
        api_key=settings.resend_api_key,
        from_email=settings.digest_from_email,
        site_url=settings.site_url,
        reply_to=settings.digest_reply_to,
        override_email=to,
    )

    print("\n" + "=" * 68)
    for k, v in result.items():
        print(f"  {k:20} {v}")
    print("=" * 68 + "\n")
    return 0 if "error" not in result else 1


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))