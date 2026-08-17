from __future__ import annotations

import time
from io import BytesIO

import httpx
import structlog
from llama_parse import LlamaParse
from tenacity import retry, stop_after_attempt, wait_exponential

from decoded.parsing.base import BaseParser, ParseResult

logger = structlog.get_logger()


class LlamaParseParser(BaseParser):
    name = "llamaparse"

    def __init__(self, api_key: str, timeout_s: float = 300.0) -> None:
        self._parser = LlamaParse(
            api_key=api_key,
            result_type="markdown",
            verbose=False,
            language="en",
            # These extraction hints matter for academic PDFs
            parsing_instruction=(
                "This is an academic research paper. "
                "Preserve section headers (Abstract, Introduction, Method, Results, etc.). "
                "Keep equations as LaTeX. "
                "Preserve figure captions and reference them clearly."
            ),
        )
        self._timeout_s = timeout_s

    @retry(
        stop=stop_after_attempt(2),
        wait=wait_exponential(multiplier=2, min=5, max=30),
        reraise=True,
    )
    async def parse(self, pdf_url: str) -> ParseResult:
        started = time.perf_counter()
        log = logger.bind(parser=self.name, pdf_url=pdf_url)
        log.info("parse.start")

        # 1. Download PDF
        async with httpx.AsyncClient(timeout=self._timeout_s) as client:
            resp = await client.get(pdf_url, follow_redirects=True)
            resp.raise_for_status()
            pdf_bytes = resp.content

        log.info("parse.pdf_downloaded", size_kb=len(pdf_bytes) // 1024)

        # 2. LlamaParse — the SDK is sync, wrap in a thread
        import asyncio
        loop = asyncio.get_running_loop()
        documents = await loop.run_in_executor(
            None,
            lambda: self._parser.load_data(
                BytesIO(pdf_bytes),
                extra_info={"file_name": "paper.pdf"},
            ),
        )

        markdown = "\n\n".join(doc.text for doc in documents)
        parse_ms = int((time.perf_counter() - started) * 1000)

        log.info("parse.done", chars=len(markdown), parse_ms=parse_ms)

        return ParseResult(
            parser=self.name,
            markdown=markdown,
            figures=[],  # LlamaParse doesn't expose structured figures in the free tier
            equations=[],
            parse_ms=parse_ms,
        )