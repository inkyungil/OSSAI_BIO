"""관계 후보 재계산, 허브 판정, 층화·split 배정 계약."""

from __future__ import annotations

from collections import Counter

import pytest
from pydantic import ValidationError

from bio_relation_workflow.preprocessing import (
    assign_splits,
    build_candidates,
    count_cooccurrence,
    hub_entities,
)
from bio_relation_workflow.schemas import (
    CandidatePair,
    CandidateSet,
    ClinicalNote,
    Entity,
    NoteCorpus,
)

SHA = "0" * 64


def _corpus(notes, entities):
    return NoteCorpus(
        source_file="x.html",
        source_sha256=SHA,
        notes=[ClinicalNote(note_id=i, text=t, entities=sorted(e)) for i, t, e in notes],
        entities=[Entity(entity_id=i, label=lbl) for i, lbl in entities],
    )


ENTITIES = [
    ("폐렴", "질병"),
    ("당뇨병", "질병"),
    ("인슐린", "약물"),
    ("발열", "증상"),
]


def test_cooccurrence_keeps_only_rule_pairs():
    corpus = _corpus(
        [("N1", "폐렴 당뇨병 인슐린 발열", ["폐렴", "당뇨병", "인슐린", "발열"])],
        ENTITIES,
    )
    keys = set(count_cooccurrence(corpus))
    # 질병-약물, 질병-증상만 남는다. 질병-질병과 약물-증상은 규칙에 없다.
    assert keys == {
        ("폐렴", "인슐린", "약물", "treats"),
        ("당뇨병", "인슐린", "약물", "treats"),
        ("폐렴", "발열", "증상", "has_symptom"),
        ("당뇨병", "발열", "증상", "has_symptom"),
    }


def test_cooccurrence_counts_distinct_notes():
    corpus = _corpus(
        [
            ("N1", "폐렴 발열", ["폐렴", "발열"]),
            ("N2", "폐렴 발열", ["폐렴", "발열"]),
        ],
        ENTITIES,
    )
    assert count_cooccurrence(corpus)[("폐렴", "발열", "증상", "has_symptom")] == [
        "N1",
        "N2",
    ]


def test_hub_ignores_diseases():
    # 질병은 모든 관계의 한쪽 끝이라 구조적으로 연결 수가 높다. 허브에서 제외한다.
    occurrences = {
        ("폐렴", "인슐린", "약물", "treats"): ["N1"],
        ("당뇨병", "인슐린", "약물", "treats"): ["N2"],
        ("폐렴", "발열", "증상", "has_symptom"): ["N1"],
    }
    assert "폐렴" not in hub_entities(occurrences, top_ratio=1.0)
    assert hub_entities(occurrences, top_ratio=0.5) == ["인슐린"]


def _pair(**overrides):
    payload = {
        "pair_id": "C001",
        "disease": "폐렴",
        "partner": "인슐린",
        "partner_label": "약물",
        "candidate_relation": "treats",
        "support": 1,
        "note_ids": ["N1"],
        "stratum": "kept",
    }
    payload.update(overrides)
    return CandidatePair(**payload)


def test_pair_requires_support_to_match_notes():
    with pytest.raises(ValidationError, match="support"):
        _pair(support=2, note_ids=["N1"])


def test_pair_requires_sorted_unique_notes():
    with pytest.raises(ValidationError, match="정렬"):
        _pair(support=2, note_ids=["N2", "N1"])


def test_pair_requires_label_matching_relation():
    with pytest.raises(ValidationError, match="상대 개체"):
        _pair(candidate_relation="has_symptom", partner_label="약물")


def test_candidate_set_rejects_duplicate_pairs():
    with pytest.raises(ValidationError, match="개체쌍"):
        CandidateSet(
            corpus_sha256=SHA,
            min_cooccur=2,
            relation_rules={},
            candidates=[_pair(), _pair(pair_id="C002")],
        )


def test_assign_splits_keeps_all_of_protected_strata():
    corpus = _corpus(
        [
            ("N1", "폐렴 인슐린 발열", ["폐렴", "인슐린", "발열"]),
            ("N2", "폐렴 인슐린 발열", ["폐렴", "인슐린", "발열"]),
            ("N3", "당뇨병 인슐린", ["당뇨병", "인슐린"]),
        ],
        ENTITIES,
    )
    built = build_candidates(corpus, min_cooccur=2)
    kept = [c for c in built.candidates if c.support >= 2]
    assigned = assign_splits(built, target_total=len(kept), seed=1)
    selected_ids = {c.pair_id for c in assigned.selected}
    assert selected_ids == {c.pair_id for c in kept}


def test_assign_splits_is_deterministic():
    corpus = _corpus(
        [
            ("N1", "폐렴 인슐린 발열", ["폐렴", "인슐린", "발열"]),
            ("N2", "당뇨병 인슐린 발열", ["당뇨병", "인슐린", "발열"]),
        ],
        ENTITIES,
    )
    first = assign_splits(build_candidates(corpus), target_total=3, seed=7)
    second = assign_splits(build_candidates(corpus), target_total=3, seed=7)
    assert [(c.pair_id, c.split) for c in first.candidates] == [
        (c.pair_id, c.split) for c in second.candidates
    ]


# --- 생성된 실제 후보 ---


def test_real_candidate_counts(candidates):
    assert len(candidates.candidates) == 123
    assert Counter(c.support for c in candidates.candidates) == {
        1: 56,
        2: 45,
        3: 17,
        4: 4,
        5: 1,
    }


def test_real_candidates_reproduce_original_edges(candidates):
    # 이 값이 어긋나면 이후 모든 평가의 전제가 무너진다.
    assert candidates.provenance["original_edges_reproduced"] == 67
    kept = [c for c in candidates.candidates if c.support >= candidates.min_cooccur]
    assert len(kept) == 67
    assert Counter(c.candidate_relation for c in kept) == {
        "treats": 37,
        "has_symptom": 30,
    }


def test_real_hubs_are_partners_only(candidates):
    diseases = {c.disease for c in candidates.candidates}
    assert candidates.hub_entities
    assert not (set(candidates.hub_entities) & diseases)


def test_real_selection_covers_every_kept_pair(candidates):
    # kept·reference 층은 전수 선정이라 표본 편향이 없다.
    kept_ids = {
        c.pair_id for c in candidates.candidates if c.support >= candidates.min_cooccur
    }
    selected_ids = {c.pair_id for c in candidates.selected}
    assert kept_ids <= selected_ids


def test_real_selection_size_and_splits(candidates):
    selected = candidates.selected
    assert len(selected) == 100
    assert all(c.split for c in selected)
    counts = Counter(c.split for c in selected)
    # 층별 반올림 때문에 20/40/40에서 1건 안쪽으로 흔들린다.
    assert abs(counts["development"] - 20) <= 2
    assert abs(counts["validation"] - 40) <= 2
    assert abs(counts["sealed_test"] - 40) <= 2


def test_every_split_contains_every_stratum(candidates):
    for split in ("development", "validation", "sealed_test"):
        strata = {c.stratum for c in candidates.selected if c.split == split}
        assert strata == {"reference", "kept_hub", "kept", "dropped_hub", "dropped"}
