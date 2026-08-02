"""모델 출력 계약. 물타기를 파싱 단계에서 막는지 확인한다."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from bio_relation_workflow.schemas import NoteEvidence, RelationVerdict

EVIDENCE = NoteEvidence(evidence_id="e1", quote="폐렴 환자가 발열을 호소", note_id="N1")


def test_relation_requires_evidence():
    with pytest.raises(ValidationError, match="근거가 필요"):
        RelationVerdict(relation="has_symptom", confidence=0.9)


def test_no_relation_may_omit_evidence():
    # 관계가 없다는 판정에는 뒷받침할 인용이 존재하지 않는다.
    verdict = RelationVerdict(relation="no_relation", confidence=0.6)
    assert verdict.evidence == []


def test_abstention_requires_reason():
    with pytest.raises(ValidationError, match="이유가 필요"):
        RelationVerdict(relation="no_relation", confidence=0.2, abstained=True)


def test_abstention_rejects_evidence():
    with pytest.raises(ValidationError, match="근거를 넣지 않습니다"):
        RelationVerdict(
            relation="no_relation",
            confidence=0.2,
            abstained=True,
            abstention_reason="노트가 관계를 진술하지 않음",
            evidence=[EVIDENCE],
        )


def test_abstention_rejects_asserted_relation():
    # "잘 모르겠지만 아마 치료 관계" 같은 물타기를 막는다.
    with pytest.raises(ValidationError, match="no_relation"):
        RelationVerdict(
            relation="treats",
            confidence=0.3,
            abstained=True,
            abstention_reason="확신 없음",
        )


def test_valid_abstention():
    verdict = RelationVerdict(
        relation="no_relation",
        confidence=0.2,
        abstained=True,
        abstention_reason="노트가 처방을 고려만 함",
    )
    assert verdict.abstained is True


def test_confidence_bounds():
    with pytest.raises(ValidationError):
        RelationVerdict(relation="no_relation", confidence=1.4)


def test_tool_requests_must_be_empty():
    with pytest.raises(ValidationError):
        RelationVerdict(
            relation="no_relation",
            confidence=0.5,
            tool_requests=[{"name": "search"}],
        )


def test_extra_fields_rejected():
    with pytest.raises(ValidationError):
        RelationVerdict(relation="no_relation", confidence=0.5, note="추가 설명")
