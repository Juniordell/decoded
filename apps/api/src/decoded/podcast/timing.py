from __future__ import annotations

import io

import structlog

logger = structlog.get_logger()


def read_duration_seconds(mp3_bytes: bytes) -> int | None:
    """
    Duração real de um MP3, incluindo arquivos concatenados.

    O mutagen lê apenas o primeiro header, então num arquivo formado
    pela concatenação de vários MP3s ele reporta a duração do primeiro
    segmento. A correção é somar os headers de cada segmento.
    """
    try:
        from mutagen.mp3 import MP3

        audio = MP3(io.BytesIO(mp3_bytes))
        naive = audio.info.length

        # Um MP3 de bitrate constante tem duração previsível pelo tamanho.
        # Se o header discorda muito, o arquivo é concatenado.
        bitrate = audio.info.bitrate or 128_000
        by_size = (len(mp3_bytes) * 8) / bitrate

        if by_size > naive * 1.5:
            logger.info(
                "timing.concatenated_detected",
                header_seconds=int(naive),
                size_seconds=int(by_size),
            )
            return int(by_size)

        return int(naive)

    except Exception as e:
        logger.warning("timing.read_failed", error=str(e))
        return None


def compute_chapters(
    script: dict,
    duration_seconds: int,
) -> list[dict]:
    """
    Distribui os capítulos ao longo da duração, proporcionalmente ao
    tamanho do texto de cada um.

    Isso é uma aproximação. A taxa de fala varia — números e siglas
    levam mais tempo por caractere que prosa corrida. Na prática o erro
    fica em poucos segundos num episódio de cinco minutos, o que é
    aceitável para navegação.

    Alinhamento exato exigiria a API de timestamps do ElevenLabs, que
    devolve posição por caractere. Vale trocar se a navegação por
    capítulo virar uso frequente.
    """
    intro = script.get("intro", "")
    chapters = script.get("chapters", [])
    outro = script.get("outro", "")

    total_chars = len(intro) + sum(len(c.get("body", "")) for c in chapters) + len(outro)

    if total_chars == 0 or duration_seconds <= 0:
        return []

    out: list[dict] = []
    cursor = len(intro)

    for chapter in chapters:
        start = int((cursor / total_chars) * duration_seconds)
        body_len = len(chapter.get("body", ""))
        end = int(((cursor + body_len) / total_chars) * duration_seconds)

        out.append(
            {
                "title": chapter.get("title", ""),
                "start_seconds": start,
                "end_seconds": end,
            }
        )
        cursor += body_len

    return out