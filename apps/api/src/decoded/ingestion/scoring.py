from __future__ import annotations

import math

# Top labs that get a bonus (fuzzy match on affiliation)
TOP_LABS = {
    "google", "deepmind", "openai", "anthropic", "meta", "microsoft research",
    "mit", "stanford", "berkeley", "carnegie mellon", "cmu",
    "eth zurich", "oxford", "cambridge", "princeton",
    "allen institute", "cohere", "hugging face",
}


def compute_priority(
    citation_count: int = 0,
    hn_mentions: int = 0,
    hn_points: int = 0,
    affiliations: list[str] | None = None,
    tldr_available: bool = False,
) -> float:
    """
    Combine signals into a single priority score (0.0 to 10.0-ish).

    Weights (tunable):
      - Citations: log-scaled, up to ~4 points
      - HN points: log-scaled, up to ~3 points
      - Top-lab affiliation: flat +2
      - TL;DR available (means S2 thought it was worth summarizing): +0.5
    """
    score = 0.0

    # Citations — logarithmic (10 citations = 1, 100 = 2, 1000 = 3)
    if citation_count > 0:
        score += min(math.log10(citation_count + 1) * 1.5, 4.0)

    # HN — combine mentions and total points
    if hn_points > 0:
        score += min(math.log10(hn_points + 1) * 1.5, 3.0)
    elif hn_mentions > 0:
        score += 0.5  # even 1 mention with 0 points is a signal

    # Top lab bonus
    affiliations = affiliations or []
    for aff in affiliations:
        aff_lower = (aff or "").lower()
        if any(lab in aff_lower for lab in TOP_LABS):
            score += 2.0
            break  # cap at one lab bonus

    # TL;DR pre-generated = S2 curator signal
    if tldr_available:
        score += 0.5

    return round(score, 3)