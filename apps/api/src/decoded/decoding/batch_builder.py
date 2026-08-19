from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Type

from pydantic import BaseModel

from decoded.decoding.batch_schemas import pydantic_to_tool
from decoded.decoding.prompts import (
    DEEP_DIVE_SYSTEM,
    FIGURE_EXPLANATION_SYSTEM,
    ONE_SENTENCE_SYSTEM,
    SIXTY_SECOND_SYSTEM,
)
from decoded.decoding.schemas import (
    DeepDive,
    FigureExplained,
    OneSentence,
    SixtySecondRead,
)
from decoded.decoding.token_utils import budget_for_full_text, truncate_to_tokens


@dataclass
class BatchRequestSpec:
    """Everything needed to build one Batch API request and later parse its result."""
    custom_id: str            # our key: "{arxiv_id}::{section}" or "{arxiv_id}::figures::{n}"
    arxiv_id: str
    section: str
    response_model: Type[BaseModel]
    tool_name: str
    request_body: dict[str, Any]

def _safe_custom_id(*parts: str | int) -> str:
    """Anthropic requires custom_id to match ^[a-zA-Z0-9_-]{1,64}$."""
    raw = "__".join(str(p) for p in parts)
    cleaned = "".join(c if c.isalnum() or c in "_-" else "_" for c in raw)
    return cleaned[:64]

def _make_request_body(
    model: str,
    system_prompt: str,
    user_content: Any,
    response_model: Type[BaseModel],
    max_tokens: int,
) -> tuple[dict[str, Any], str]:
    """Build the params dict for one Batch API request. Returns (body, tool_name)."""
    tool = pydantic_to_tool(response_model)
    tool_name = tool["name"]

    body = {
        "model": model,
        "max_tokens": max_tokens,
        "system": [
            {
                "type": "text",
                "text": system_prompt,
                "cache_control": {"type": "ephemeral"},
            }
        ],
        "messages": [{"role": "user", "content": user_content}],
        "tools": [tool],
        # force the model to use our tool — guarantees structured output
        "tool_choice": {"type": "tool", "name": tool_name},
    }
    return body, tool_name


def build_one_sentence_request(
    arxiv_id: str, title: str, abstract: str, model: str
) -> BatchRequestSpec:
    user = f"Paper title: {title}\n\nPaper abstract:\n{abstract}"
    body, tool_name = _make_request_body(
        model=model,
        system_prompt=ONE_SENTENCE_SYSTEM,
        user_content=user,
        response_model=OneSentence,
        max_tokens=200,
    )
    return BatchRequestSpec(
        custom_id=_safe_custom_id(arxiv_id, "one_sentence"),
        arxiv_id=arxiv_id,
        section="one_sentence",
        response_model=OneSentence,
        tool_name=tool_name,
        request_body=body,
    )


def build_sixty_second_request(
    arxiv_id: str, title: str, abstract: str, model: str
) -> BatchRequestSpec:
    user = f"Paper title: {title}\n\nPaper abstract:\n{abstract}"
    body, tool_name = _make_request_body(
        model=model,
        system_prompt=SIXTY_SECOND_SYSTEM,
        user_content=user,
        response_model=SixtySecondRead,
        max_tokens=1000,
    )
    return BatchRequestSpec(
        custom_id=_safe_custom_id(arxiv_id, "sixty_second"),
        arxiv_id=arxiv_id,
        section="sixty_second",
        response_model=SixtySecondRead,
        tool_name=tool_name,
        request_body=body,
    )


def build_deep_dive_request(
    arxiv_id: str, title: str, abstract: str, full_text: str, model: str
) -> BatchRequestSpec:
    budget = budget_for_full_text(title, abstract, DEEP_DIVE_SYSTEM)
    safe_text = truncate_to_tokens(full_text, budget)

    user = (
        f"Paper title: {title}\n\n"
        f"Paper abstract:\n{abstract}\n\n"
        f"---\n\nFull paper text (parsed from PDF):\n\n{safe_text}"
    )
    body, tool_name = _make_request_body(
        model=model,
        system_prompt=DEEP_DIVE_SYSTEM,
        user_content=user,
        response_model=DeepDive,
        max_tokens=4000,
    )
    return BatchRequestSpec(
        custom_id=_safe_custom_id(arxiv_id, "deep_dive"),
        arxiv_id=arxiv_id,
        section="deep_dive",
        response_model=DeepDive,
        tool_name=tool_name,
        request_body=body,
    )


def build_figure_requests(
    arxiv_id: str,
    figures_data: list[dict],
    model: str,
) -> list[BatchRequestSpec]:
    """One request per figure. Results merged back into a single figures section."""
    specs: list[BatchRequestSpec] = []

    for idx, fig in enumerate(figures_data):
        user_content = [
            {
                "type": "image",
                "source": {
                    "type": "base64",
                    "media_type": fig["media_type"],
                    "data": fig["image_b64"],
                },
            },
            {
                "type": "text",
                "text": f"Text from the same page (for context):\n\n{fig['nearby_text']}",
            },
        ]
        body, tool_name = _make_request_body(
            model=model,
            system_prompt=FIGURE_EXPLANATION_SYSTEM,
            user_content=user_content,
            response_model=FigureExplained,
            max_tokens=800,
        )
        specs.append(
            BatchRequestSpec(
                custom_id=_safe_custom_id(arxiv_id, "figures", idx),
                arxiv_id=arxiv_id,
                section="figures",
                response_model=FigureExplained,
                tool_name=tool_name,
                request_body=body,
            )
        )

    return specs