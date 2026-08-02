"""복사한 문자열 함수가 원본과 같은 값을 내는지 지킨다.

원본 `src/verifiable_ai_workflow/evaluation/scoring.py`의 동작이 기준이다. 여기서
값이 달라지면 원본에서 가져온 근거 대조·환각 검사의 성질이 바뀐 것이다.
"""

from __future__ import annotations

import pytest

from bio_relation_workflow.evaluation.text_metrics import (
    best_quote_similarity,
    contains_fact,
    edit_similarity,
    normalize,
    numbers,
    similarity,
    token_f1,
    tokens,
)


def test_normalize_strips_punctuation_and_case():
    assert normalize("SpO₂ 91 %, 폐렴!") == normalize("spo291폐렴")


def test_numbers_reads_decimals_and_negatives():
    assert numbers("CRP 8.2 mg/dL, 변화 -1.5") == ["8.2", "-1.5"]


def test_similarity_is_one_for_equal_after_normalize():
    assert similarity("폐렴 소견", "폐렴  소견!!") == 1.0


def test_edit_similarity_handles_empty():
    assert edit_similarity("", "") == 1.0
    assert edit_similarity("폐렴", "") == 0.0


def test_edit_similarity_is_normalized_distance():
    assert edit_similarity("abcd", "abcd") == 1.0
    assert edit_similarity("abcd", "abce") == pytest.approx(0.75)


def test_tokens_split_by_script():
    assert tokens("폐렴 pneumonia 91%") == ["폐렴", "pneumonia", "91"]


def test_token_f1_full_and_partial():
    assert token_f1("폐렴 발열", "발열 폐렴") == 1.0
    assert 0.0 < token_f1("폐렴 발열", "폐렴 기침") < 1.0


def test_best_quote_similarity_exact_substring():
    source = "폐렴 환자가 발열와(과) 기침을(를) 호소하여 흉부 X선를 시행하였다."
    assert best_quote_similarity("발열와(과) 기침을(를) 호소", source) == 1.0


def test_best_quote_similarity_detects_fabrication():
    source = "폐렴 환자가 발열을 호소하였다."
    assert best_quote_similarity("와파린을 투여하여 협심증이 호전되었다", source) < 0.5


def test_best_quote_similarity_empty_inputs():
    assert best_quote_similarity("", "본문") == 0.0
    assert best_quote_similarity("인용", "") == 0.0


def test_contains_fact_uses_numbers_when_present():
    assert contains_fact("SpO2 91 %", "91") is True
    assert contains_fact("SpO2 95 %", "91") is False


def test_contains_fact_falls_back_to_text():
    assert contains_fact("폐렴 소견이 있다", "폐렴") is True
    assert contains_fact("천식 소견이 있다", "폐렴") is False
