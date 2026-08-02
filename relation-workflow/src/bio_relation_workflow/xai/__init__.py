"""근거 절제로 사후 설명의 충실도를 재는 텍스트 축 XAI."""

from .ablation import (
    NOT_APPLICABLE,
    SENTENCE_MATCH_THRESHOLD,
    AblationOutcome,
    Faithfulness,
    ablate_notes,
    classify,
    evidence_sentences,
    score_ablation,
    split_sentences,
)

__all__ = [
    "NOT_APPLICABLE",
    "SENTENCE_MATCH_THRESHOLD",
    "AblationOutcome",
    "Faithfulness",
    "ablate_notes",
    "classify",
    "evidence_sentences",
    "score_ablation",
    "split_sentences",
]
