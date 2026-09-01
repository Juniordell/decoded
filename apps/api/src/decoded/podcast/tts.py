"""Síntese de voz via ElevenLabs.

Gera capítulo por capítulo em vez de um bloco único. Dois motivos:
o limite de caracteres por requisição, e a possibilidade de regenerar
um capítulo isolado quando ele sai ruim.
"""

from __future__ import annotations

import asyncio
import io
from dataclasses import dataclass, field

import structlog
from tenacity import retry, stop_after_attempt, wait_exponential

logger = structlog.get_logger()

# Preço do tier Starter: $5 por 30.000 caracteres
COST_PER_CHAR = 5.0 / 30_000

# Limite prático por requisição no modelo turbo
MAX_CHARS_PER_REQUEST = 4000


@dataclass
class AudioSegment:
    label: str
    text: str
    audio: bytes
    char_count: int
    duration_seconds: float = 0.0


@dataclass
class SynthesisResult:
    segments: list[AudioSegment] = field(default_factory=list)
    total_chars: int = 0
    cost_usd: float = 0.0

    @property
    def total_duration_seconds(self) -> int:
        return int(sum(s.duration_seconds for s in self.segments))

    @property
    def combined_audio(self) -> bytes:
        """
        MP3s concatenados byte a byte.

        Isso funciona porque MP3 é um formato de frames — players
        toleram concatenação simples. Não é tecnicamente perfeito
        (headers duplicados), mas é o que a maioria dos pipelines faz,
        e nenhum player que testamos reclama.
        """
        return b"".join(s.audio for s in self.segments)


class ElevenLabsClient:
    def __init__(
        self,
        api_key: str,
        voice_id: str,
        model: str = "eleven_turbo_v2_5",
    ) -> None:
        from elevenlabs.client import ElevenLabs

        self._client = ElevenLabs(api_key=api_key)
        self._voice_id = voice_id
        self._model = model

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=2, min=4, max=30),
        reraise=True,
    )
    async def _synthesize_chunk(self, text: str) -> bytes:
        """
        O SDK é síncrono e retorna um generator de bytes.
        Roda em thread para não bloquear o event loop.
        """
        loop = asyncio.get_running_loop()

        def _call() -> bytes:
            stream = self._client.text_to_speech.convert(
                voice_id=self._voice_id,
                model_id=self._model,
                text=text,
                output_format="mp3_44100_128",
                voice_settings={
                    # Estabilidade alta mantém o tom consistente entre
                    # capítulos — importante porque eles são gerados
                    # em requisições separadas
                    "stability": 0.55,
                    "similarity_boost": 0.75,
                    "style": 0.0,
                    "use_speaker_boost": True,
                },
            )
            buffer = io.BytesIO()
            for chunk in stream:
                if chunk:
                    buffer.write(chunk)
            return buffer.getvalue()

        return await loop.run_in_executor(None, _call)

    def _split_long(self, text: str) -> list[str]:
        """Divide em fronteira de frase quando passa do limite."""
        if len(text) <= MAX_CHARS_PER_REQUEST:
            return [text]

        sentences = text.replace("! ", "!|").replace("? ", "?|").replace(". ", ".|")
        parts = [s.strip() for s in sentences.split("|") if s.strip()]

        chunks: list[str] = []
        current = ""

        for sentence in parts:
            candidate = f"{current} {sentence}".strip()
            if len(candidate) > MAX_CHARS_PER_REQUEST and current:
                chunks.append(current)
                current = sentence
            else:
                current = candidate

        if current:
            chunks.append(current)

        return chunks

    async def synthesize_script(self, script: dict) -> SynthesisResult:
        """
        Sintetiza o roteiro inteiro, um segmento por vez.

        A ordem importa: intro, capítulos na sequência, outro.
        """
        result = SynthesisResult()

        blocks: list[tuple[str, str]] = [("intro", script.get("intro", ""))]
        for i, chapter in enumerate(script.get("chapters", []), 1):
            blocks.append(
                (f"chapter_{i}:{chapter.get('title', '')}", chapter.get("body", ""))
            )
        blocks.append(("outro", script.get("outro", "")))

        for label, text in blocks:
            if not text.strip():
                continue

            for chunk in self._split_long(text):
                logger.info("tts.synthesizing", label=label, chars=len(chunk))
                audio = await self._synthesize_chunk(chunk)

                seg_duration = 0.0
                try:
                    from mutagen.mp3 import MP3
                    seg_duration = MP3(io.BytesIO(audio)).info.length
                except Exception:
                    pass

                result.segments.append(
                    AudioSegment(
                        label=label,
                        text=chunk,
                        audio=audio,
                        char_count=len(chunk),
                        duration_seconds=seg_duration,
                    )
                )
                result.total_chars += len(chunk)

        result.cost_usd = result.total_chars * COST_PER_CHAR

        logger.info(
            "tts.done",
            segments=len(result.segments),
            chars=result.total_chars,
            bytes=len(result.combined_audio),
            cost_usd=round(result.cost_usd, 4),
        )

        return result