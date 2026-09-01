"""Geração do feed RSS.

Podcast RSS é RSS 2.0 mais a extensão iTunes. Apple e Spotify validam
o feed antes de aceitar, e campos faltando causam rejeição — daí o
cuidado com os obrigatórios.
"""

from __future__ import annotations

import html
from datetime import datetime, timezone
from email.utils import format_datetime

ITUNES_NS = "http://www.itunes.com/dtds/podcast-1.0.dtd"
CONTENT_NS = "http://purl.org/rss/1.0/modules/content/"
ATOM_NS = "http://www.w3.org/2005/Atom"


def _esc(text: str | None) -> str:
    return html.escape(text or "", quote=True)


def _rfc2822(dt: datetime) -> str:
    """RSS exige RFC 2822, não ISO 8601."""
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return format_datetime(dt)


def _duration(seconds: int) -> str:
    """Formato HH:MM:SS que o iTunes espera."""
    h, rem = divmod(max(seconds, 0), 3600)
    m, s = divmod(rem, 60)
    return f"{h:02d}:{m:02d}:{s:02d}" if h else f"{m:02d}:{s:02d}"


def build_feed(
    episodes: list[dict],
    site_url: str,
    feed_url: str,
    cover_url: str,
    author: str = "Nelson Dell",
    email: str = "nelson@readdecoded.com",
) -> str:
    """
    Monta o feed.

    episodes espera dicts com: arxiv_id, title, description, audio_url,
    duration_seconds, size_bytes, published_at.
    """
    now = _rfc2822(datetime.now(timezone.utc))

    items: list[str] = []
    for ep in episodes:
        arxiv_id = _esc(ep["arxiv_id"])
        page_url = f"{site_url}/paper/{arxiv_id}"

        items.append(f"""    <item>
      <title>{_esc(ep["title"])}</title>
      <link>{page_url}</link>
      <guid isPermaLink="false">decoded-{arxiv_id}</guid>
      <pubDate>{_rfc2822(ep["published_at"])}</pubDate>
      <description>{_esc(ep.get("description") or ep["title"])}</description>
      <enclosure url="{_esc(ep["audio_url"])}" length="{ep.get("size_bytes", 0)}" type="audio/mpeg" />
      <itunes:duration>{_duration(ep.get("duration_seconds", 0))}</itunes:duration>
      <itunes:explicit>false</itunes:explicit>
      <itunes:episodeType>full</itunes:episodeType>
      <itunes:summary>{_esc(ep.get("description") or ep["title"])}</itunes:summary>
    </item>""")

    items_xml = "\n".join(items)

    return f"""<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0"
     xmlns:itunes="{ITUNES_NS}"
     xmlns:content="{CONTENT_NS}"
     xmlns:atom="{ATOM_NS}">
  <channel>
    <title>Decoded</title>
    <link>{site_url}</link>
    <atom:link href="{_esc(feed_url)}" rel="self" type="application/rss+xml" />
    <description>Every AI paper, explained for humans. New research from arXiv, decoded into something you can actually follow — in three to eight minutes.</description>
    <language>en-us</language>
    <copyright>© {datetime.now().year} {_esc(author)}</copyright>
    <lastBuildDate>{now}</lastBuildDate>
    <generator>Decoded</generator>

    <itunes:author>{_esc(author)}</itunes:author>
    <itunes:summary>Every AI paper, explained for humans. New research from arXiv, decoded into something you can actually follow.</itunes:summary>
    <itunes:type>episodic</itunes:type>
    <itunes:explicit>false</itunes:explicit>
    <itunes:image href="{_esc(cover_url)}" />
    <itunes:owner>
      <itunes:name>{_esc(author)}</itunes:name>
      <itunes:email>{_esc(email)}</itunes:email>
    </itunes:owner>
    <itunes:category text="Technology" />
    <itunes:category text="Science">
      <itunes:category text="Mathematics" />
    </itunes:category>

{items_xml}
  </channel>
</rss>"""