from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field


@dataclass
class ParseResult:
    """What every parser returns."""
    parser: str
    markdown: str
    figures: list[dict] = field(default_factory=list)  # [{page: 3, caption: "...", ...}]
    equations: list[dict] = field(default_factory=list)  # [{page: 4, latex: "...", ...}]
    parse_ms: int = 0


class BaseParser(ABC):
    """Contract every parser must satisfy."""

    name: str

    @abstractmethod
    async def parse(self, pdf_url: str) -> ParseResult:
        """Download PDF from URL, parse, return structured result."""
        ...