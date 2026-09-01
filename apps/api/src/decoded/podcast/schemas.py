from __future__ import annotations

from pydantic import BaseModel, Field

PODCAST_SCHEMA_VERSION = 1


class ScriptChapter(BaseModel):
    """Um trecho do episódio, com marcador de capítulo."""

    title: str = Field(
        ...,
        description="Título curto do capítulo, aparece no player",
        max_length=80,
    )
    body: str = Field(
        ...,
        description="O texto a ser falado. Sem markdown, sem símbolos.",
        max_length=4000,
    )


class PodcastScript(BaseModel):
    intro: str = Field(
        ...,
        description="Abertura. 2-3 frases dizendo o que vem pela frente.",
        max_length=800,
    )
    chapters: list[ScriptChapter] = Field(
        ...,
        description="Corpo do episódio, dividido em capítulos",
        max_length=6,
    )
    outro: str = Field(
        ...,
        description="Fecho. Uma frase de encerramento e o que fica em aberto.",
        max_length=500,
    )

    estimated_seconds: int = Field(
        default=0,
        description="Duração estimada, calculada a partir da contagem de caracteres",
    )

    @property
    def full_text(self) -> str:
        parts = [self.intro]
        for c in self.chapters:
            parts.append(c.body)
        parts.append(self.outro)
        return "\n\n".join(parts)

    @property
    def chapter_offsets(self) -> list[tuple[str, int]]:
        """
        Offset aproximado de cada capítulo em caracteres.

        Vira timestamp depois que o áudio existe e a duração real é conhecida.
        """
        offsets: list[tuple[str, int]] = []
        cursor = len(self.intro) + 2

        for c in self.chapters:
            offsets.append((c.title, cursor))
            cursor += len(c.body) + 2

        return offsets