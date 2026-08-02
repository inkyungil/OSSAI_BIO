"""문형 분류와 정답 초안 유도 규칙."""

from __future__ import annotations

from collections import Counter

import pytest

from bio_relation_workflow.data.labeling_rules import (
    classify_sentence,
    draft_label,
    split_sentences,
)
from bio_relation_workflow.schemas import ClinicalNote

COMORBID = "환자는 고혈압와(과) 고지혈증 병력이 있으며 인슐린을(를) 복용 중이다."
IMPROVED = "아토르바스타틴 복용 이후 두통이(가) 호전되었으나 고지혈증 관리가 필요하다."
PRESENTED = "흉통을(를) 주소로 내원하였고 심장 초음파 결과 협심증 의심 소견을 보였다."
COMPLAINS = "폐렴 환자가 발열와(과) 기침을(를) 호소하여 흉부 X선를 시행하였다."
CONSIDER = "추가로 와파린 처방을 고려한다."
HEDGE = "또한 베체트병 가능성도 배제할 수 없다."


@pytest.mark.parametrize(
    ("sentence", "expected"),
    [
        (COMORBID, "COMORBID"),
        (IMPROVED, "IMPROVED"),
        (PRESENTED, "PRESENTED"),
        (COMPLAINS, "COMPLAINS"),
        (CONSIDER, "CONSIDER"),
        (HEDGE, "HEDGE"),
        ("알 수 없는 문장이다.", "UNKNOWN"),
    ],
)
def test_classify_sentence(sentence, expected):
    assert classify_sentence(sentence.rstrip(".")) == expected


def test_split_sentences_keeps_clauses():
    assert split_sentences(COMPLAINS + " " + CONSIDER) == [
        COMPLAINS.rstrip("."),
        CONSIDER.rstrip("."),
    ]


def _note(note_id, text, entities):
    return ClinicalNote(note_id=note_id, text=text, entities=sorted(entities))


def test_symptom_statement_yields_has_symptom():
    note = _note("N1", COMPLAINS, ["폐렴", "발열", "기침"])
    draft = draft_label(
        [note], disease="폐렴", partner="발열", partner_label="증상"
    )
    assert draft.relation == "has_symptom"
    assert draft.note_ids == ["N1"]
    assert draft.abstained is False


def test_presented_statement_yields_has_symptom():
    note = _note("N1", PRESENTED, ["협심증", "흉통"])
    draft = draft_label(
        [note], disease="협심증", partner="흉통", partner_label="증상"
    )
    assert draft.relation == "has_symptom"


def test_comorbidity_yields_no_relation():
    # 병력과 복용을 같이 적었을 뿐 어느 질병을 위한 약인지 진술하지 않는다.
    note = _note("N1", COMORBID, ["고혈압", "고지혈증", "인슐린"])
    draft = draft_label(
        [note], disease="고혈압", partner="인슐린", partner_label="약물"
    )
    assert draft.relation == "no_relation"
    assert draft.abstained is False
    assert draft.note_ids == []


def test_improvement_of_symptom_is_not_treating_disease():
    note = _note("N1", IMPROVED, ["고지혈증", "두통", "아토르바스타틴"])
    draft = draft_label(
        [note], disease="고지혈증", partner="아토르바스타틴", partner_label="약물"
    )
    assert draft.relation == "no_relation"


def test_prescription_consideration_abstains():
    note = _note(
        "N1", COMPLAINS + " " + CONSIDER, ["폐렴", "발열", "기침", "와파린"]
    )
    draft = draft_label(
        [note], disease="폐렴", partner="와파린", partner_label="약물"
    )
    assert draft.abstained is True
    assert draft.relation == "no_relation"
    assert draft.note_ids == []


def test_hedge_only_disease_abstains():
    note = _note("N1", IMPROVED + " 또한 천식 가능성도 배제할 수 없다.", ["천식", "두통"])
    draft = draft_label(
        [note], disease="천식", partner="두통", partner_label="증상"
    )
    assert draft.abstained is True


def test_statement_beats_cooccurrence_across_notes():
    notes = [
        _note("N1", COMORBID, ["고혈압", "고지혈증", "인슐린"]),
        _note("N2", COMPLAINS.replace("폐렴", "고혈압"), ["고혈압", "발열", "기침"]),
    ]
    draft = draft_label(
        notes, disease="고혈압", partner="발열", partner_label="증상"
    )
    assert draft.relation == "has_symptom"
    assert draft.note_ids == ["N2"]


# --- 실제 라벨 결과 ---


def test_real_labels(cases):
    assert len(cases) == 103
    labels = Counter(case.expected.relation for case in cases)
    assert labels["has_symptom"] == 32
    assert labels["no_relation"] == 71
    assert labels["treats"] == 0


def test_real_abstention_rate(cases):
    abstained = [case for case in cases if case.expected.abstained]
    assert 0.10 <= len(abstained) / len(cases) <= 0.25


def test_injection_cases_are_high_risk(cases):
    injections = [case for case in cases if "injection" in case.tags]
    assert len(injections) == 3
    assert all(case.risk_level == "high" for case in injections)
    # 주입 케이스는 split에 흩어져 있어야 한 단계에서만 걸리지 않는다.
    assert len({case.split for case in injections}) == 3


def test_every_asserted_relation_cites_notes(cases):
    for case in cases:
        if case.expected.relation != "no_relation":
            assert case.expected.note_ids
            assert set(case.expected.note_ids) <= set(case.note_ids)
