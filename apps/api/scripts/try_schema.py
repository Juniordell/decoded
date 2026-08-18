"""Round-trip test the decoded schemas."""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from decoded.decoding.schemas import (
    Analogies, Analogy, DecodedPaper, DeepDive, DeepDiveSection,
    FigureExplained, FiguresExplained, OneSentence, SixtySecondRead,
    SoWhat, VocabTerm, Vocabulary,
)


def main() -> None:
    paper = DecodedPaper(
        one_sentence=OneSentence(text="The paper shows a language model can learn to reason by arguing with itself."),
        sixty_second=SixtySecondRead(
            problem="Language models are bad at multi-step math reasoning.",
            approach="Have the model generate two answers, then critique its own reasoning.",
            result="Accuracy on GSM8K jumped from 82 to 93 percent with the self-debate approach.",
        ),
        deep_dive=DeepDive(
            setup=DeepDiveSection(heading="Setup", body="Prior work..."),
            idea=DeepDiveSection(heading="Idea", body="The insight..."),
            method=DeepDiveSection(heading="Method", body="Two forward passes..."),
            results=DeepDiveSection(heading="Results", body="93% on GSM8K, 87% on MATH."),
            implications=DeepDiveSection(heading="Implications", body="Reasoning is compute-scalable."),
        ),
        vocabulary=Vocabulary(terms=[
            VocabTerm(term="GSM8K", definition="A benchmark of grade-school math word problems."),
            VocabTerm(term="Chain-of-thought", definition="Prompting a model to show its reasoning step by step."),
        ]),
        analogies=Analogies(items=[
            Analogy(
                concept="Self-debate",
                analogy="Like asking two lawyers to argue both sides before making up your mind.",
            ),
        ]),
        figures=FiguresExplained(items=[
            FigureExplained(
                figure_ref="Figure 3",
                caption_from_paper="Accuracy vs. number of debate rounds.",
                plain_language="More rounds of debate help, but only up to about 3. After that, gains stop.",
                key_insight="Debate helps, but there's a plateau — more compute past 3 rounds is wasted.",
            ),
        ]),
        so_what=SoWhat(
            matters_because="Simple prompting trick with meaningful accuracy gains, no fine-tuning required.",
            who_benefits="Anyone building math/coding assistants can plug this in today.",
            open_question="Does self-debate generalize to non-math domains like legal reasoning?",
        ),
    )

    # Round-trip through JSON to verify serialization
    as_json = paper.model_dump(mode="json")
    print(json.dumps(as_json, indent=2))
    print(f"\nSize: {len(json.dumps(as_json))} chars")

    # Deserialize back
    restored = DecodedPaper.model_validate(as_json)
    assert restored.one_sentence.text == paper.one_sentence.text
    print("\nRound-trip OK.")


if __name__ == "__main__":
    main()