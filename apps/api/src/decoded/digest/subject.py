from __future__ import annotations

import instructor
import structlog
from anthropic import AsyncAnthropic
from pydantic import BaseModel, Field

from decoded.decoding.generator import _compute_cost

logger = structlog.get_logger()


class DigestSubject(BaseModel):
    subject: str = Field(
        ...,
        description="Assunto do email, 4-9 palavras",
        max_length=90,
    )
    preview: str = Field(
        ...,
        description="Texto de preview, aparece ao lado do assunto na inbox",
        max_length=120,
    )


SUBJECT_SYSTEM = """You write subject lines for a weekly email about AI research papers.

You receive the papers selected for this week's email. Write a subject line and a preview line.

RULES FOR THE SUBJECT:

- 4 to 9 words.
- Name the single most interesting thing in the email. Not a summary of everything.
- Concrete over abstract. A specific finding beats a category.
- No "This week in AI", "Your weekly digest", "AI roundup" — the reader knows what this is.
- No emoji. No exclamation marks. No ALL CAPS.
- Sentence case, not Title Case.
- A number or a surprising claim earns the open. "Benchmarks are inflated by 30%" beats "New findings on evaluation."

GOOD SUBJECTS:
- Reasoning benchmarks are mostly memorization
- A 7B model matching GPT-4 on code
- Why long context still fails past 50k tokens
- Three labs converged on the same trick
- The attention bottleneck nobody talks about

BAD SUBJECTS:
- Your weekly AI digest is here          (says nothing)
- 6 papers you should read this week     (generic, could be any newsletter)
- Exciting new developments in AI!       (hype, exclamation)
- Papers on RLHF, Attention, and More    (a list, not a hook)

RULES FOR THE PREVIEW:

One sentence naming what else is in the email. It appears next to the subject in the inbox, so it should add information rather than repeat.

Good: "Plus a survey that finds most agent benchmarks are unreproducible."
Bad: "Read the latest papers in artificial intelligence research."

WHEN THE PAPERS DON'T SHARE A THEME:

That's normal. Pick the single most striking paper for the subject and use the preview to signal breadth. Don't force a false connection.

OUTPUT: return the structured object. No preamble."""


class SubjectWriter:
    def __init__(self, api_key: str, model: str) -> None:
        self._raw = AsyncAnthropic(api_key=api_key)
        self._client = instructor.from_anthropic(self._raw)
        self._model = model
        self.total_cost = 0.0

    async def close(self) -> None:
        await self._raw.close()

    async def __aenter__(self) -> "SubjectWriter":
        return self

    async def __aexit__(self, *args) -> None:
        await self.close()

    async def write(self, papers: list[dict]) -> DigestSubject:
        lines = []
        for p in papers[:8]:
            lines.append(f"- {p['title']}")
            if p.get("one_sentence"):
                lines.append(f"  {p['one_sentence']}")

        user = "Papers in this week's email:\n\n" + "\n".join(lines)

        result, raw = await self._client.messages.create_with_completion(
            model=self._model,
            max_tokens=300,
            system=[
                {
                    "type": "text",
                    "text": SUBJECT_SYSTEM,
                    "cache_control": {"type": "ephemeral"},
                }
            ],
            messages=[{"role": "user", "content": user}],
            response_model=DigestSubject,
            max_retries=2,
        )

        usage = (
            raw.usage.model_dump()
            if hasattr(raw.usage, "model_dump")
            else dict(raw.usage)
        )
        self.total_cost += _compute_cost(usage, self._model)

        return result