"""운영점 라우팅과 임계값 선택. 규율을 코드가 강제하는지까지 고정한다."""

from __future__ import annotations

import pytest

from bio_relation_workflow.evaluation.operating_point import (
    confidence_calibration,
    evaluate_operating_point,
    route_case,
    select_operating_point,
    sweep,
)
from bio_relation_workflow.schemas import (
    EvaluationResult,
    ExpectedRelation,
    RelationCase,
    RelationVerdict,
)

SOURCE = {"title": "t", "license": "l", "revision": "r"}


def _case(sample_id: str, *, support: int = 2, expected: ExpectedRelation, split="validation"):
    return RelationCase(
        sample_id=sample_id,
        family_id="폐렴",
        pair_id=sample_id,
        disease="폐렴",
        partner="발열",
        partner_label="증상",
        candidate_relation="has_symptom",
        support=support,
        note_ids=["N1"],
        split=split,
        stratum="kept",
        risk_level="medium",
        source=SOURCE,
        expected=expected,
    )


def _result(sample_id: str, *, verdict: RelationVerdict | None, split="validation"):
    return EvaluationResult(
        sample_id=sample_id,
        family_id="폐렴",
        split=split,
        status="passed",
        output=verdict,
        scores={},
        reasons={},
        evidence_kind="live_quality",
    )


def _asserted(confidence: float, relation: str = "has_symptom") -> RelationVerdict:
    return RelationVerdict(
        relation=relation,
        evidence=[{"evidence_id": "e1", "quote": "발열", "note_id": "N1"}],
        confidence=confidence,
    )


def _negative(confidence: float) -> RelationVerdict:
    return RelationVerdict(relation="no_relation", confidence=confidence)


def _abstained() -> RelationVerdict:
    return RelationVerdict(
        relation="no_relation",
        confidence=0.0,
        abstained=True,
        abstention_reason="노트가 애매하다",
    )


# --- 라우팅 ---


def test_support_below_cut_is_filtered_before_the_model():
    case = _case("C1", support=1, expected=ExpectedRelation(relation="no_relation"))
    result = _result("C1", verdict=_asserted(1.0))
    assert route_case(case, result, min_cooccur=2, min_confidence=0.5) == "filtered"


def test_low_confidence_assertion_goes_to_review_queue():
    case = _case("C1", expected=ExpectedRelation(relation="has_symptom", note_ids=["N1"]))
    result = _result("C1", verdict=_asserted(0.7))
    assert route_case(case, result, min_cooccur=1, min_confidence=0.9) == "review_queue"


def test_abstention_goes_to_review_queue_at_any_threshold():
    case = _case("C1", expected=ExpectedRelation(relation="no_relation", abstained=True))
    result = _result("C1", verdict=_abstained())
    assert route_case(case, result, min_cooccur=1, min_confidence=0.0) == "review_queue"


def test_schema_failure_goes_to_review_queue_not_dropped():
    """판정이 없는 건을 조용히 버리면 실패가 보이지 않는다."""
    case = _case("C1", expected=ExpectedRelation(relation="has_symptom", note_ids=["N1"]))
    result = _result("C1", verdict=None)
    assert route_case(case, result, min_cooccur=1, min_confidence=0.9) == "review_queue"


def test_confident_no_relation_is_dropped_silently():
    case = _case("C1", expected=ExpectedRelation(relation="no_relation"))
    result = _result("C1", verdict=_negative(0.95))
    assert route_case(case, result, min_cooccur=1, min_confidence=0.9) == "auto_drop"


# --- 집계 ---


def test_silent_miss_counts_gold_positive_dropped_confidently():
    cases = [_case("C1", expected=ExpectedRelation(relation="has_symptom", note_ids=["N1"]))]
    results = [_result("C1", verdict=_negative(0.99))]
    cell = evaluate_operating_point(cases, results, min_cooccur=1, min_confidence=0.9)
    assert cell["auto_drop"] == 1
    assert cell["silent_miss"] == 1
    assert cell["ppv"] is None


def test_filtered_gold_positive_is_also_a_silent_miss():
    """잡음컷에 걸려 사라진 진짜 관계도 사람이 못 본다 — 같은 비용이다."""
    cases = [
        _case(
            "C1",
            support=1,
            expected=ExpectedRelation(relation="has_symptom", note_ids=["N1"]),
        )
    ]
    results = [_result("C1", verdict=_asserted(1.0))]
    cell = evaluate_operating_point(cases, results, min_cooccur=2, min_confidence=0.5)
    assert cell["silent_miss"] == 1
    assert cell["silent_miss_by_filter"] == 1


def test_ppv_counts_only_shown_relations():
    cases = [
        _case("C1", expected=ExpectedRelation(relation="has_symptom", note_ids=["N1"])),
        _case("C2", expected=ExpectedRelation(relation="no_relation")),
        _case("C3", expected=ExpectedRelation(relation="no_relation")),
    ]
    results = [
        _result("C1", verdict=_asserted(0.95)),
        _result("C2", verdict=_asserted(0.95)),  # 헛경보
        _result("C3", verdict=_negative(0.95)),  # 화면에 안 뜸
    ]
    cell = evaluate_operating_point(cases, results, min_cooccur=1, min_confidence=0.9)
    assert cell["auto_show"] == 2
    assert cell["ppv"] == 0.5
    assert cell["recall_shown"] == 1.0


def test_queue_precision_measures_wasted_human_time():
    cases = [
        _case("C1", expected=ExpectedRelation(relation="has_symptom", note_ids=["N1"])),
        _case("C2", expected=ExpectedRelation(relation="no_relation")),
    ]
    results = [
        _result("C1", verdict=_asserted(0.5)),
        _result("C2", verdict=_negative(0.5)),
    ]
    cell = evaluate_operating_point(cases, results, min_cooccur=1, min_confidence=0.9)
    assert cell["review_queue"] == 2
    assert cell["queue_precision"] == 0.5


# --- 선택 규율 ---


def test_sweep_rejects_non_validation_split():
    """임계값을 sealed_test에서 고르면 평가셋이 선택셋이 된다 (day5 p37-38)."""
    cases = [
        _case(
            "C1",
            split="sealed_test",
            expected=ExpectedRelation(relation="has_symptom", note_ids=["N1"]),
        )
    ]
    results = [_result("C1", verdict=_asserted(0.95), split="sealed_test")]
    with pytest.raises(ValueError, match="validation"):
        sweep(cases, results)


def test_selection_respects_ppv_floor_before_coverage():
    grid = [
        {
            "min_cooccur": 1,
            "min_confidence": 0.5,
            "auto_show": 10,
            "auto_show_correct": 8,
            "ppv": 0.8,
            "silent_miss": 0,
            "review_queue": 0,
        },
        {
            "min_cooccur": 1,
            "min_confidence": 0.9,
            "auto_show": 5,
            "auto_show_correct": 5,
            "ppv": 1.0,
            "silent_miss": 3,
            "review_queue": 5,
        },
    ]
    chosen = select_operating_point(grid, ppv_floor=0.95)
    # 자동표시 수가 적어도 제약을 지키는 쪽을 고른다.
    assert chosen["min_confidence"] == 0.9


def test_selection_fails_loudly_when_no_cell_meets_the_constraint():
    grid = [
        {
            "min_cooccur": 1,
            "min_confidence": 0.5,
            "auto_show": 4,
            "auto_show_correct": 2,
            "ppv": 0.5,
            "silent_miss": 0,
            "review_queue": 0,
        }
    ]
    with pytest.raises(ValueError, match="PPV"):
        select_operating_point(grid, ppv_floor=0.95)


def test_calibration_exposes_flat_confidence():
    """정답률이 confidence에 따라 변하지 않으면 임계값은 손잡이가 아니다."""
    cases = [
        _case("C1", expected=ExpectedRelation(relation="no_relation")),
        _case("C2", expected=ExpectedRelation(relation="no_relation")),
    ]
    results = [
        _result("C1", verdict=_negative(0.9)),
        _result("C2", verdict=_negative(1.0)),
    ]
    rows = confidence_calibration(cases, results)
    assert [row["accuracy"] for row in rows] == [1.0, 1.0]
