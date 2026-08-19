from __future__ import annotations

import base64
import io
from dataclasses import dataclass, field
from typing import Iterator

import fitz  # PyMuPDF
import httpx
import structlog

logger = structlog.get_logger()

# Skip tiny "figures" (logos, decorative marks) and enormous ones (whole pages).
MIN_IMAGE_WIDTH_PX = 200
MIN_IMAGE_HEIGHT_PX = 150
MAX_IMAGE_BYTES = 5 * 1024 * 1024   # 5 MB — Anthropic's per-image limit
MAX_FIGURES_PER_PAPER = 6           # cost control


@dataclass
class ExtractedFigure:
    """One image extracted from the PDF."""
    page_number: int              # 1-indexed
    figure_index: int             # nth figure on the page
    width: int
    height: int
    image_bytes: bytes            # PNG or JPEG bytes
    media_type: str               # "image/png" or "image/jpeg"
    nearby_text: str = ""         # text on the same page (helps identify captions)

    @property
    def figure_ref(self) -> str:
        return f"page {self.page_number} · image {self.figure_index}"

    def to_b64(self) -> str:
        return base64.standard_b64encode(self.image_bytes).decode("ascii")


@dataclass
class ExtractionResult:
    figures: list[ExtractedFigure] = field(default_factory=list)
    total_pages: int = 0
    total_images_found: int = 0
    skipped_small: int = 0
    skipped_large: int = 0


async def download_pdf(pdf_url: str, timeout_s: float = 60.0) -> bytes:
    async with httpx.AsyncClient(timeout=timeout_s) as client:
        resp = await client.get(pdf_url, follow_redirects=True)
        resp.raise_for_status()
        return resp.content


def extract_figures_from_pdf_bytes(
    pdf_bytes: bytes,
    max_figures: int = MAX_FIGURES_PER_PAPER,
) -> ExtractionResult:
    """Open a PDF from bytes, extract raster images, return filtered figures."""
    doc = fitz.open(stream=pdf_bytes, filetype="pdf")
    result = ExtractionResult(total_pages=len(doc))

    for page_index, page in enumerate(doc):
        page_number = page_index + 1
        page_text = page.get_text("text")

        for fig_idx, img_info in enumerate(page.get_images(full=True), start=1):
            result.total_images_found += 1
            xref = img_info[0]
            try:
                pix = fitz.Pixmap(doc, xref)

                # Convert CMYK / alpha weirdness to RGB
                if pix.n - pix.alpha > 3:
                    pix = fitz.Pixmap(fitz.csRGB, pix)

                width, height = pix.width, pix.height

                if width < MIN_IMAGE_WIDTH_PX or height < MIN_IMAGE_HEIGHT_PX:
                    result.skipped_small += 1
                    pix = None
                    continue

                image_bytes = pix.tobytes("png")
                pix = None  # release the Pixmap

                if len(image_bytes) > MAX_IMAGE_BYTES:
                    result.skipped_large += 1
                    continue

                result.figures.append(
                    ExtractedFigure(
                        page_number=page_number,
                        figure_index=fig_idx,
                        width=width,
                        height=height,
                        image_bytes=image_bytes,
                        media_type="image/png",
                        nearby_text=page_text[:1500],
                    )
                )

                if len(result.figures) >= max_figures:
                    doc.close()
                    return result

            except Exception as e:
                logger.warning(
                    "figure.extract_error",
                    page=page_number,
                    fig_idx=fig_idx,
                    error=str(e),
                )
                continue

    doc.close()
    return result


def iter_figures_from_pdf_bytes(
    pdf_bytes: bytes,
    max_figures: int = MAX_FIGURES_PER_PAPER,
) -> Iterator[ExtractedFigure]:
    """Streaming variant if you ever want to process one figure at a time."""
    result = extract_figures_from_pdf_bytes(pdf_bytes, max_figures=max_figures)
    yield from result.figures