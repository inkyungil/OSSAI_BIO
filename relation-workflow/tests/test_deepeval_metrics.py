"""DeepEval TestRun 생성과 지표 임계값 규율."""

from __future__ import annotations

import json

from bio_relation_workflow.evaluation.deepeval_runner import (
    METRIC_SPECS,
    deterministic_metrics,
    evaluate_results,
)
from bio_relation_workflow.evaluation.relation_scoring import (
    SCORE_NAMES,
    score_observations,
)
from bio_relation_workflow.schemas import (
    ExpectedRelation,
    ModelObservation,
    RelationCase,
)

NOTE_TEXT = {"N1": "폐렴 환자가 발열와(과) 기침을(를) 호소하여 흉부 X선를 시행하였다."}
SOURCE = {"title": "t", "license": "l", "revision": "r"}


def _case():
    return RelationCase(
        sample_id="C001-폐렴-발열",
        family_id="폐렴",
        pair_id="C001",
        disease="폐렴",
        partner="발열",
        partner_label="증상",
        candidate_relation="has_symptom",
        support=1,
        note_ids=["N1"],
        split="development",
        stratum="kept",
        risk_level="medium",
        source=SOURCE,
        expected=ExpectedRelation(relation="has_symptom", note_ids=["N1"]),
    )


def _results(evidence_kind="test_only"):
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
            "confidence": 0.9,
            "abstained": False,
        },
        evidence_kind=evidence_kind,
    )
    return [case], score_observations([case], [observation], note_texts=NOTE_TEXT)


def test_metric_specs_cover_every_score():
    assert {name for name, _, _ in METRIC_SPECS} == set(SCORE_NAMES)


def test_only_required_metrics_gate():
    # 진단용 지표는 threshold 0. pass/fail은 task_success가 결정한다.
    gating = {name for name, _, threshold in METRIC_SPECS if threshold == 1.0}
    assert gating == {
        "schema_validity",
        "relation_correct",
        "abstention_correct",
        "note_id_valid",
        "evidence_note_hit",
        # 인용 게이트는 task_success와 같은 필수 조건이다. 평균(quote_grounding)이
        # 아니라 통과 여부가 걸린다.
        "quote_gate",
        "task_success",
    }


def test_metrics_measure_from_results():
    _, results = _results()
    metrics = deterministic_metrics(results)
    assert len(metrics) == len(METRIC_SPECS)


def test_evaluate_results_writes_testrun(tmp_path):
    cases, results = _results()
    folder = tmp_path / "deepeval"
    evaluate_results(results, cases, folder)
    written = list(folder.glob("*.json"))
    assert written, "TestRun 파일이 생성되지 않았습니다"
    payload = json.loads(written[0].read_text(encoding="utf-8"))
    assert payload
