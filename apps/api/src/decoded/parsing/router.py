from __future__ import annotations

import structlog

from decoded.db.models import Paper
from decoded.parsing.base import BaseParser
from decoded.parsing.llamaparse import LlamaParseParser

logger = structlog.get_logger()

# Math-heavy arXiv categories where Nougat would win (once we add it)
MATH_HEAVY_CATEGORIES = {"math.", "stat.ML", "cs.LO", "quant-ph"}


class ParserRouter:
    """
    Picks the best parser for a given paper.

    Right now everything goes to LlamaParse. The routing hooks are here so
    we can plug in Nougat/Docling later without touching the ingestion code.
    """

    def __init__(self, llamaparse_api_key: str) -> None:
        self._llamaparse = LlamaParseParser(api_key=llamaparse_api_key)
        # self._nougat = NougatParser(...)   # Day XX
        # self._docling = DoclingParser(...) # Day XX

    def pick(self, paper: Paper) -> BaseParser:
        """Return the parser instance for this paper."""
        # Future: check math density → Nougat
        # if self._is_math_heavy(paper):
        #     return self._nougat

        # Future: check figure density → Docling
        # if self._is_figure_heavy(paper):
        #     return self._docling

        return self._llamaparse

    def _is_math_heavy(self, paper: Paper) -> bool:
        cats = paper.categories or []
        return any(c.startswith(prefix) for c in cats for prefix in MATH_HEAVY_CATEGORIES)