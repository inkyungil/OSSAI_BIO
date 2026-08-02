"""관계 채점기. 정답·오답·보류·환각 각 경우를 고정한다."""

from __future__ import annotations

import pytest

from bio_relation_workflow.evaluation.relation_scoring import (
    parse_output,
    score_observations,
    score_output,
)
from bio_relation_workflow.schemas import (
    ExpectedRelation,
    ModelObservation,
    RelationCase,
)

NOTE_TEXT = {
    "N1": "폐렴 환자가 발열와(과) 기침을(를) 호소하여 흉부 X선를 시행하였다.",
    "N2": "환자는 폐렴와(과) 위염 병력이 있으며 아스피린을(를) 복용 중이다.",
}
SOURCE = {"title": "t", "license": "l", "revision": "r"}


def _case(**overrides):
    payload = {
        "sample_id": "C001-폐렴-발열",
        "family_id": "폐렴",
        "pair_id": "C001",
        "disease": "폐렴",
        "partner": "발열",
        "partner_label": "증상",
        "candidate_relation": "has_symptom",
        "support": 1,
        "note_ids": ["N1"],
        "split": "development",
        "stratum": "kept",
        "risk_level": "medium",
        "source": SOURCE,
        "expected": ExpectedRelation(relation="has_symptom", note_ids=["N1"]),
    }
    payload.update(overrides)
    return RelationCase(**payload)


def _verdict(**overrides):
    payload = {
        "relation": "has_symptom",
        "evidence": [
            {
                "evidence_id": "e1",
                "quote": "발열와(과) 기침을(를) 호소하여",
                "note_id": "N1",
            }
        ],
        "confidence": 0.9,
        "abstained": False,
    }
    payload.update(overrides)
    return payload


def _score(raw, case=None):
    return score_output(raw, case or _case(), note_texts=NOTE_TEXT)


def test_parse_output_strips_markdown_fence():
    verdict = parse_output('```json\n{"relation":"no_relation","confidence":0.5}\n```')
    assert verdict.relation == "no_relation"


def test_correct_answer_passes_every_gate():
    _, scores, _, halluc = _score(_verdict())
    assert scores["task_success"] == 1.0
    assert scores["quote_grounding"] == 1.0
    assert halluc == []


def test_broken_json_is_schema_failure():
    verdict, scores, reasons, _ = _score("이건 JSON이 아닙니다")
    assert verdict is None
    assert scores["schema_validity"] == 0.0
    assert scores["task_success"] == 0.0
    assert "JSONDecodeError" in reasons["schema_validity"]


def test_markdown_fence_lowers_json_object_only_but_still_parses():
    _, scores, _, _ = _score(
        '```json\n' + '{"relation":"no_relation","confidence":0.5}' + '\n```'
    )
    assert scores["json_object_only"] == 0.0
    assert scores["schema_validity"] == 1.0


def test_wrong_relation_is_relation_hallucination():
    case = _case(expected=ExpectedRelation(relation="no_relation"))
    _, scores, _, halluc = _score(_verdict(), case)
    assert scores["relation_correct"] == 0.0
    assert scores["task_success"] == 0.0
    assert "RELATION" in halluc


def test_missing_relation_is_omission():
    _, scores, _, halluc = _score(
        _verdict(relation="no_relation", evidence=[]),
    )
    assert scores["relation_correct"] == 0.0
    assert "OMISSION" in halluc


def test_note_outside_candidate_is_source_hallucination():
    _, scores, reasons, halluc = _score(
        _verdict(
            evidence=[
                {"evidence_id": "e1", "quote": "무언가", "note_id": "N9"}
            ]
        )
    )
    assert scores["note_id_valid"] == 0.0
    assert scores["task_success"] == 0.0
    assert "SOURCE" in halluc
    assert "N9" in reasons["note_id_valid"]


def test_fabricated_quote_fails_grounding_gate():
    # 원본과 달리 검증 불가를 이유로 gate를 건너뛰지 않는다.
    _, scores, _, halluc = _score(
        _verdict(
            evidence=[
                {
                    "evidence_id": "e1",
                    "quote": "아스피린 투여로 폐렴이 완치되었다",
                    "note_id": "N1",
                }
            ]
        )
    )
    assert scores["quote_grounding"] < 0.8
    assert scores["task_success"] == 0.0
    assert "SOURCE" in halluc


def test_evidence_note_hit_requires_overlap_with_gold():
    case = _case(
        note_ids=["N1", "N2"],
        support=2,
        expected=ExpectedRelation(relation="has_symptom", note_ids=["N1"]),
    )
    _, scores, _, _ = _score(
        _verdict(
            evidence=[
                {
                    "evidence_id": "e1",
                    "quote": "폐렴와(과) 위염 병력이 있으며",
                    "note_id": "N2",
                }
            ]
        ),
        case,
    )
    assert scores["evidence_note_hit"] == 0.0
    assert scores["task_success"] == 0.0


def test_abstention_matching_gold_passes():
    case = _case(expected=ExpectedRelation(relation="no_relation", abstained=True))
    _, scores, _, _ = _score(
        _verdict(
            relation="no_relation",
            evidence=[],
            abstained=True,
            abstention_reason="노트가 처방을 고려만 함",
            confidence=0.2,
        ),
        case,
    )
    assert scores["abstention_correct"] == 1.0
    assert scores["task_success"] == 1.0


def test_answering_when_gold_abstains_fails():
    case = _case(expected=ExpectedRelation(relation="no_relation", abstained=True))
    _, scores, _, _ = _score(_verdict(), case)
    assert scores["abstention_correct"] == 0.0
    assert scores["task_success"] == 0.0


def test_reference_agreement_is_diagnostic_only():
    case = _case(in_reference=True, expected=ExpectedRelation(relation="no_relation"))
    _, scores, reasons, _ = _score(
        _verdict(relation="no_relation", evidence=[]), case
    )
    # 참조표와 어긋나도 task_success를 깎지 않는다. 참조표는 세 번째 의견이다.
    assert scores["reference_agreement"] == 0.0
    assert scores["relation_correct"] == 1.0
    assert scores["task_success"] == 1.0
    assert "참조표" in reasons["reference_agreement"]


def test_reference_agreement_skipped_when_unknown():
    _, scores, reasons, _ = _score(_verdict())
    assert scores["reference_agreement"] == 1.0
    assert "대조하지 않은" in reasons["reference_agreement"]


def test_model_error_is_inconclusive():
    case = _case()
    observation = ModelObservation(
        sample_id=case.sample_id,
        family_id=case.family_id,
        split=case.split,
        known_note_ids=case.note_ids,
        model_error="APIError: timeout",
        evidence_kind="live_quality",
    )
    result = score_observations([case], [observation], note_texts=NOTE_TEXT)[0]
    assert result.status == "inconclusive"
    assert result.scores["task_success"] == 0.0
    assert result.evidence_kind == "live_quality"


def test_score_observations_carries_evidence_kind_and_split():
    case = _case()
    observation = ModelObservation(
        sample_id=case.sample_id,
        family_id=case.family_id,
        split=case.split,
        known_note_ids=case.note_ids,
        raw_output=_verdict(),
        evidence_kind="test_only",
    )
    result = score_observations([case], [observation], note_texts=NOTE_TEXT)[0]
    assert result.status == "passed"
    assert result.evidence_kind == "test_only"
    assert result.split == "development"


@pytest.mark.parametrize("name", ["treats", "has_symptom", "no_relation"])
def test_every_relation_label_is_scorable(name):
    case = _case(
        expected=ExpectedRelation(
            relation=name,
            note_ids=[] if name == "no_relation" else ["N1"],
        )
    )
    payload = _verdict(relation=name)
    if name == "no_relation":
        payload["evidence"] = []
    _, scores, _, _ = _score(payload, case)
    assert scores["relation_correct"] == 1.0
