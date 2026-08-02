"""근거 절제 — 입력 만들기와 충실도 분류 (day6 p17, p22)."""

from __future__ import annotations

from bio_relation_workflow.schemas import (
    ClinicalNote,
    ExpectedRelation,
    RelationCase,
    RelationVerdict,
)
from bio_relation_workflow.xai import (
    NOT_APPLICABLE,
    ablate_notes,
    classify,
    evidence_sentences,
    score_ablation,
    split_sentences,
)

SOURCE = {"title": "t", "license": "l", "revision": "r"}

TWO_SENTENCE = ClinicalNote(
    note_id="N1",
    text=(
        "발열을(를) 주소로 내원하였고 혈액검사 결과 고혈압 의심 소견을 보였다. "
        "또한 모야모야병 가능성도 배제할 수 없다."
    ),
)
OTHER = ClinicalNote(
    note_id="N2",
    text="환자는 고혈압와(과) 고지혈증 병력이 있으며 인슐린을(를) 복용 중이다.",
)


def _case(**overrides):
    payload = {
        "sample_id": "C030-고혈압-발열",
        "family_id": "고혈압",
        "pair_id": "C030",
        "disease": "고혈압",
        "partner": "발열",
        "partner_label": "증상",
        "candidate_relation": "has_symptom",
        "support": 2,
        "note_ids": ["N1", "N2"],
        "split": "validation",
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
                "quote": "발열을(를) 주소로 내원하였고",
                "note_id": "N1",
            }
        ],
        "confidence": 0.95,
        "abstained": False,
    }
    payload.update(overrides)
    return RelationVerdict(**payload)


# --- 입력 만들기 ---


def test_splits_sentences_without_losing_text():
    parts = split_sentences(TWO_SENTENCE.text)
    assert len(parts) == 2
    assert "".join(parts).replace(" ", "") == TWO_SENTENCE.text.replace(" ", "")


def test_partial_quote_recovers_its_whole_sentence():
    cited, rest = evidence_sentences(TWO_SENTENCE, ["발열을(를) 주소로 내원하였고"])
    assert len(cited) == 1
    assert cited[0].startswith("발열을(를) 주소로")
    assert rest == ["또한 모야모야병 가능성도 배제할 수 없다."]


def test_quote_spanning_two_sentences_recovers_both():
    """실제 실행에서 나온 결함 — 한쪽 포함만 보면 근거문장을 하나도 못 찾는다."""
    cited, rest = evidence_sentences(TWO_SENTENCE, [TWO_SENTENCE.text])
    assert len(cited) == 2
    assert rest == []


def test_multi_sentence_quote_leaves_nothing_for_comprehensiveness():
    verdict = _verdict(
        evidence=[
            {"evidence_id": "e1", "quote": TWO_SENTENCE.text, "note_id": "N1"}
        ]
    )
    assert ablate_notes([TWO_SENTENCE], verdict, mode="comprehensiveness") == []
    assert len(ablate_notes([TWO_SENTENCE], verdict, mode="sufficiency")) == 1


def test_sufficiency_keeps_only_cited_sentences():
    ablated = ablate_notes([TWO_SENTENCE, OTHER], _verdict(), mode="sufficiency")
    assert [note.note_id for note in ablated] == ["N1"]
    assert "모야모야병" not in ablated[0].text
    assert "발열" in ablated[0].text


def test_comprehensiveness_removes_only_cited_sentences():
    ablated = ablate_notes([TWO_SENTENCE, OTHER], _verdict(), mode="comprehensiveness")
    by_id = {note.note_id: note.text for note in ablated}
    assert "발열" not in by_id["N1"]
    assert "모야모야병" in by_id["N1"]
    # 인용되지 않은 노트는 필요성 쪽에 그대로 남는다.
    assert by_id["N2"] == OTHER.text


def test_note_disappears_when_all_of_it_was_evidence():
    single = ClinicalNote(note_id="N3", text="폐렴 환자가 흉통을(를) 호소하여 시행하였다.")
    verdict = _verdict(
        evidence=[
            {
                "evidence_id": "e1",
                "quote": "폐렴 환자가 흉통을(를) 호소하여 시행하였다.",
                "note_id": "N3",
            }
        ]
    )
    assert ablate_notes([single], verdict, mode="comprehensiveness") == []


def test_note_ids_are_preserved_so_results_can_be_compared():
    ablated = ablate_notes([TWO_SENTENCE], _verdict(), mode="sufficiency")
    assert ablated[0].note_id == "N1"


# --- 충실도 분류 ---


def test_four_way_classification():
    assert classify(sufficient=True, necessary=True) == "FAITHFUL"
    assert classify(sufficient=True, necessary=False) == "REDUNDANT"
    assert classify(sufficient=False, necessary=True) == "PARTIAL"
    assert classify(sufficient=False, necessary=False) == "DECORATIVE"


def test_evidence_that_changes_nothing_is_decorative():
    """근거만 줘도 판정이 다르고, 근거를 빼도 판정이 그대로면 장식이다."""
    outcome = score_ablation(
        _case(),
        _verdict(),
        sufficiency=RelationVerdict(relation="no_relation", confidence=0.5),
        comprehensiveness=_verdict(),
    )
    assert outcome.sufficient is False
    assert outcome.necessary is False
    assert outcome.faithfulness == "DECORATIVE"


def test_evidence_that_carries_the_verdict_is_faithful():
    outcome = score_ablation(
        _case(),
        _verdict(),
        sufficiency=_verdict(),
        comprehensiveness=RelationVerdict(relation="no_relation", confidence=0.5),
    )
    assert outcome.faithfulness == "FAITHFUL"


def test_abstention_difference_is_not_the_same_verdict():
    """둘 다 no_relation이어도 한쪽이 보류면 같은 판정이 아니다."""
    original = RelationVerdict(
        relation="no_relation",
        evidence=[{"evidence_id": "e1", "quote": "발열", "note_id": "N1"}],
        confidence=0.9,
    )
    outcome = score_ablation(
        _case(),
        original,
        sufficiency=RelationVerdict(
            relation="no_relation",
            confidence=0.3,
            abstained=True,
            abstention_reason="문장만으로는 가릴 수 없다",
        ),
        comprehensiveness=original,
    )
    assert outcome.sufficient is False
    assert outcome.necessary is False


def test_whole_note_evidence_is_not_counted_as_faithful():
    """빈 입력으로는 어떤 판정도 재현될 수 없다. 자동으로 참이 되는 필요성을
    FAITHFUL로 세면 충실도가 부풀려진다."""
    outcome = score_ablation(
        _case(),
        _verdict(),
        sufficiency=_verdict(),
        comprehensiveness=None,
        necessity_vacuous=True,
    )
    assert outcome.faithfulness == "NECESSITY_VACUOUS"
    # 충분성은 실제로 쟀으므로 남는다.
    assert outcome.sufficient is True
    assert outcome.necessary is None


def test_no_evidence_means_nothing_to_ablate():
    outcome = score_ablation(
        _case(),
        RelationVerdict(relation="no_relation", confidence=0.9),
        sufficiency=None,
        comprehensiveness=None,
    )
    assert outcome.faithfulness == NOT_APPLICABLE
    assert "절제할 것이 없다" in outcome.note
