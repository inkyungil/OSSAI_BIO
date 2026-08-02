"""근거문장 절제 — 텍스트 축 XAI (`day6 p6` 지형도의 빈칸, `day6 p17` 정량화).

Grad-CAM은 픽셀 히트맵이라 텍스트에 붙지 않는다. 대신 모델이 든 근거문장을 실제로
빼거나 남겨서 판정이 어떻게 변하는지를 잰다. vision 쪽 deletion metric과 같은 발상이다.

| 지표 | 입력 | 묻는 것 |
| --- | --- | --- |
| **충분성** sufficiency | 근거문장 **만** | 그 문장만으로 같은 판정이 나오나 |
| **필요성** comprehensiveness | 근거문장을 **뺀** 나머지 | 빼면 판정이 뒤집히나 |

근거를 뺐는데도 판정이 그대로면 그 인용은 **사후에 갖다 붙인 장식**이다. 모델은 다른
것을 보고 결정했고 인용은 구색이었다는 뜻이다. `day6 p17`의 "사후 설명은 인과가 아님"에
대한 정량적 답이며, 결정적으로 채점되므로 LLM Judge가 필요 없다.

비용은 케이스 1건당 API 2회다. 근거를 인용하지 않은 판정(보류·무근거 no_relation)은
절제할 것이 없으므로 대상에서 빠진다.
"""

from __future__ import annotations

import re
from typing import Literal

from ..evaluation.text_metrics import best_quote_similarity, normalize
from ..schemas import ClinicalNote, Contract, RelationCase, RelationVerdict

# 인용문이 이 문장에서 나왔다고 인정하는 기준. 채점의 QUOTE_THRESHOLD와 같은 값을
# 쓴다 — 근거로 인정한 인용을 절제 대상으로도 인정해야 앞뒤가 맞는다.
SENTENCE_MATCH_THRESHOLD = 0.8

Faithfulness = Literal[
    "FAITHFUL",  # 충분하고 필요하다 — 그 문장이 판정을 만들었다
    "REDUNDANT",  # 충분하지만 없어도 된다 — 같은 결론을 낼 근거가 더 있다
    "PARTIAL",  # 그것만으로는 부족하지만 빠지면 무너진다
    "DECORATIVE",  # 충분하지도 필요하지도 않다 — 장식
    # 인용문이 노트 전부여서 "빼고 묻기"가 성립하지 않는다. 빈 입력으로는 어떤 판정도
    # 재현될 수 없으므로 필요성이 자동으로 참이 되는데, 그것은 측정이 아니라 동어반복이다.
    # FAITHFUL로 세면 충실도가 부풀려진다.
    "NECESSITY_VACUOUS",
]

# 절제할 근거가 없어 재질의가 성립하지 않는 경우.
NOT_APPLICABLE = "NOT_APPLICABLE"


def split_sentences(text: str) -> list[str]:
    """노트를 문장으로 나눈다. 구분자를 잃지 않아야 되돌려 붙일 수 있다."""
    parts = re.split(r"(?<=[.!?])\s+", text.strip())
    return [part for part in parts if part.strip()]


def evidence_sentences(
    note: ClinicalNote,
    quotes: list[str],
) -> tuple[list[str], list[str]]:
    """노트를 (근거문장, 나머지 문장)으로 가른다.

    인용문은 문장의 일부일 수도, 여러 문장에 걸칠 수도 있다. 그래서 포함을 양방향으로
    본다 — 인용문이 문장 안에 있거나(부분 인용), 문장이 인용문 안에 있거나(여러 문장을
    통째로 인용). 한쪽만 보면 두 문장짜리 인용에서 근거문장을 하나도 못 찾는다.
    """
    sentences = split_sentences(note.text)
    cited: list[str] = []
    rest: list[str] = []
    for sentence in sentences:
        normalized = normalize(sentence)
        hit = any(
            normalize(quote) in normalized
            or (normalized and normalized in normalize(quote))
            or best_quote_similarity(quote, sentence) >= SENTENCE_MATCH_THRESHOLD
            for quote in quotes
        )
        (cited if hit else rest).append(sentence)
    return cited, rest


def ablate_notes(
    notes: list[ClinicalNote],
    verdict: RelationVerdict,
    *,
    mode: Literal["sufficiency", "comprehensiveness"],
) -> list[ClinicalNote]:
    """절제한 노트 집합을 만든다.

    sufficiency        — 인용된 문장만 남긴다
    comprehensiveness  — 인용된 문장만 지운다

    note_id는 그대로 둔다. 모델이 원래와 같은 note_id로 인용할 수 있어야 두 결과를
    비교할 수 있다.
    """
    quotes_by_note: dict[str, list[str]] = {}
    for item in verdict.evidence:
        quotes_by_note.setdefault(item.note_id, []).append(item.quote)

    ablated: list[ClinicalNote] = []
    for note in notes:
        quotes = quotes_by_note.get(note.note_id)
        if not quotes:
            # 인용되지 않은 노트 — 충분성에서는 통째로 빠지고 필요성에서는 남는다.
            if mode == "comprehensiveness":
                ablated.append(note)
            continue
        cited, rest = evidence_sentences(note, quotes)
        kept = cited if mode == "sufficiency" else rest
        if kept:
            ablated.append(
                ClinicalNote(
                    note_id=note.note_id,
                    text=" ".join(kept),
                    entities=note.entities,
                )
            )
    return ablated


class AblationOutcome(Contract):
    """한 케이스의 절제 결과. 두 번의 재질의를 하나로 묶는다."""

    sample_id: str
    split: str
    original_relation: str
    original_abstained: bool
    evidence_note_ids: list[str]
    sufficiency_relation: str | None = None
    comprehensiveness_relation: str | None = None
    sufficient: bool | None = None
    necessary: bool | None = None
    faithfulness: Faithfulness | str = NOT_APPLICABLE
    note: str = ""


def classify(*, sufficient: bool, necessary: bool) -> Faithfulness:
    if sufficient and necessary:
        return "FAITHFUL"
    if sufficient and not necessary:
        return "REDUNDANT"
    if not sufficient and necessary:
        return "PARTIAL"
    return "DECORATIVE"


def score_ablation(
    case: RelationCase,
    original: RelationVerdict,
    *,
    sufficiency: RelationVerdict | None,
    comprehensiveness: RelationVerdict | None,
    necessity_vacuous: bool = False,
) -> AblationOutcome:
    """두 재질의 결과를 원래 판정과 대조한다.

    같은 판정인지는 relation과 보류 여부를 함께 본다. `no_relation`으로 수렴했는데
    한쪽은 보류였다면 같은 판정이 아니다.

    `necessity_vacuous`는 인용문이 노트 전부여서 뺄 것이 남지 않는 경우다. 이때
    필요성은 물어보나 마나 참이므로 측정으로 세지 않는다.
    """
    outcome = AblationOutcome(
        sample_id=case.sample_id,
        split=case.split,
        original_relation=original.relation,
        original_abstained=original.abstained,
        evidence_note_ids=sorted({item.note_id for item in original.evidence}),
    )
    if not original.evidence:
        outcome.note = "인용한 근거가 없어 절제할 것이 없다"
        return outcome
    if sufficiency is None:
        outcome.note = "충분성 재질의 응답이 없거나 파싱되지 않았다"
        return outcome

    same = (original.relation, original.abstained)
    outcome.sufficiency_relation = sufficiency.relation
    outcome.sufficient = (sufficiency.relation, sufficiency.abstained) == same

    if necessity_vacuous:
        # 충분성은 실제로 쟀지만 필요성은 물어볼 수 없다. 둘을 합친 4분류를 붙이지 않는다.
        outcome.faithfulness = "NECESSITY_VACUOUS"
        outcome.note = "인용문이 노트 전부여서 필요성을 물을 수 없다"
        return outcome
    if comprehensiveness is None:
        outcome.note = "필요성 재질의 응답이 없거나 파싱되지 않았다"
        return outcome
    outcome.comprehensiveness_relation = comprehensiveness.relation
    # 필요성은 "빼면 뒤집힌다"이므로 같지 **않아야** 참이다.
    outcome.necessary = (comprehensiveness.relation, comprehensiveness.abstained) != same
    outcome.faithfulness = classify(
        sufficient=outcome.sufficient, necessary=outcome.necessary
    )
    return outcome
