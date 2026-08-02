"""요약이 보고 의무를 지키는지. 빠뜨리면 결과를 잘못 읽게 되는 항목들이다.

원본 `scripts/evaluate_workflow.py:62`가 evidence_kind를 하드코딩해 live 결과를
test_only로 찍는 문제가 있었다. 여기서는 그런 항목을 테스트로 못 박는다.
"""

from __future__ import annotations

import pytest

from bio_relation_workflow.evaluation import build_summary, score_observations
from bio_relation_workflow.schemas import (
    ExpectedRelation,
    ModelObservation,
    RelationCase,
)

SOURCE = {"title": "t", "license": "l", "revision": "r"}
NOTE_TEXT = {"N1": "폐렴 환자가 발열와(과) 기침을(를) 호소하여 흉부 X선를 시행하였다."}

# 결과 보고에 반드시 있어야 하는 것 여섯. 각각 어느 규율에서 왔는지가 근거다.
REQUIRED_KEYS = (
    "evidence_kind",  # day5 p53 — 모델 품질인가 코드 회귀인가
    "asserted_relation",  # day3 p35-36 — 화면에 뜬 것 중 맞은 비율(PPV)
    "hallucinations",  # day5 p21 — 환각 4분류 분포
    "generalization",  # day5 p39 — 일반화 사다리 위치
    "routing_counts",  # day5 p51 — 자동확정이 없다는 증거
    "injection",  # day5 p52 — 주입 탐지·저항
)


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
        "split": "sealed_test",
        "stratum": "kept",
        "risk_level": "medium",
        "source": SOURCE,
        "expected": ExpectedRelation(relation="has_symptom", note_ids=["N1"]),
    }
    payload.update(overrides)
    return RelationCase(**payload)


def _summary(evidence_kind="live_quality"):
    case = _case()
    observation = ModelObservation(
        sample_id=case.sample_id,
        family_id=case.family_id,
        split=case.split,
        known_note_ids=case.note_ids,
        raw_output={
            "relation": "has_symptom",
            "evidence": [
                {
                    "evidence_id": "e1",
                    "quote": "발열와(과) 기침을(를) 호소하여",
                    "note_id": "N1",
                }
            ],
            "confidence": 0.95,
            "abstained": False,
            "abstention_reason": None,
            "tool_requests": [],
        },
        evidence_kind=evidence_kind,
    )
    results = score_observations([case], [observation], note_texts=NOTE_TEXT)
    return build_summary(results, [case], requested_model="m")


def test_summary_carries_every_required_item():
    summary = _summary()
    missing = [key for key in REQUIRED_KEYS if key not in summary]
    assert not missing, f"보고 의무 항목이 빠졌습니다: {missing}"


def test_ppv_is_reported_separately_from_accuracy():
    """전체 정확도는 no_relation이 많아 높게 나온다. 화면 품질은 PPV가 말한다."""
    summary = _summary()
    assert "ppv" in summary["asserted_relation"]
    assert "recall" in summary["asserted_relation"]


def test_evidence_kind_comes_from_observations_not_a_constant():
    assert _summary("live_quality")["evidence_kind"] == "live_quality"
    assert _summary("test_only")["evidence_kind"] == "test_only"


def test_no_routing_path_reaches_approval():
    """day5 p51 — PASS는 확정이 아니다."""
    summary = _summary()
    assert all("APPROVED" not in key for key in summary["routing_counts"])


def test_generalization_level_is_stated():
    assert _summary()["generalization"].startswith("SINGLE")


def test_empty_results_are_refused_rather_than_summarized():
    with pytest.raises(ValueError):
        build_summary([], [], requested_model="m")
