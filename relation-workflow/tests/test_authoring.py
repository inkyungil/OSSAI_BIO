"""라벨링 편집 틀과 평가 케이스 변환 계약."""

from __future__ import annotations

import pytest
import yaml
from pydantic import ValidationError

from bio_relation_workflow.data import (
    build_cases,
    build_labeling_template,
    split_note_overlap,
    write_labeling_template,
)
from bio_relation_workflow.schemas import ExpectedRelation, RelationCase

SOURCE = {"title": "t", "license": "l", "revision": "r"}


def test_expected_rejects_abstain_with_notes():
    with pytest.raises(ValidationError, match="보류"):
        ExpectedRelation(relation="no_relation", note_ids=["N1"], abstained=True)


def test_expected_rejects_abstain_with_relation():
    with pytest.raises(ValidationError, match="보류"):
        ExpectedRelation(relation="treats", note_ids=[], abstained=True)


def test_expected_requires_notes_when_relation_asserted():
    with pytest.raises(ValidationError, match="근거 노트"):
        ExpectedRelation(relation="treats", note_ids=[])


def test_expected_allows_no_relation_without_notes():
    assert ExpectedRelation(relation="no_relation").note_ids == []


def _case(**overrides):
    payload = {
        "sample_id": "C001-폐렴-아스피린",
        "family_id": "폐렴",
        "pair_id": "C001",
        "disease": "폐렴",
        "partner": "아스피린",
        "partner_label": "약물",
        "candidate_relation": "treats",
        "support": 1,
        "note_ids": ["N1"],
        "split": "development",
        "stratum": "kept",
        "risk_level": "medium",
        "source": SOURCE,
        "expected": ExpectedRelation(relation="treats", note_ids=["N1"]),
    }
    payload.update(overrides)
    return RelationCase(**payload)


def test_case_rejects_evidence_outside_candidate_notes():
    with pytest.raises(ValidationError, match="후보의 등장 노트 밖"):
        _case(expected=ExpectedRelation(relation="treats", note_ids=["N9"]))


def test_template_leaves_only_expected_blank(candidates, corpus):
    template = build_labeling_template(candidates, corpus, source=SOURCE)
    assert len(template["cases"]) == len(candidates.selected)
    first = template["cases"][0]
    assert first["expected"] == {
        "relation": "TODO",
        "note_ids": [],
        "abstained": False,
    }
    # 판정에 필요한 노트 전문이 틀 안에 들어 있어야 원본을 열지 않고 라벨링할 수 있다.
    assert all(note["text"] for note in first["notes"])
    assert len(first["notes"]) == first["support"]


def test_build_cases_refuses_unlabeled(tmp_path, candidates, corpus):
    path = tmp_path / "cases.yaml"
    write_labeling_template(
        build_labeling_template(candidates, corpus, source=SOURCE), path
    )
    with pytest.raises(ValueError, match="라벨이 비어 있는"):
        build_cases(path)


def test_build_cases_reads_labeled_template(tmp_path, candidates, corpus):
    template = build_labeling_template(candidates, corpus, source=SOURCE)
    for case in template["cases"]:
        case["expected"] = {
            "relation": "no_relation",
            "note_ids": [],
            "abstained": False,
        }
    path = tmp_path / "cases.yaml"
    write_labeling_template(template, path)
    cases = build_cases(path)
    assert len(cases) == len(candidates.selected)
    assert {case.family_id for case in cases} <= {c.disease for c in candidates.selected}


def test_build_cases_rejects_wrong_schema_version(tmp_path):
    path = tmp_path / "cases.yaml"
    path.write_text(
        yaml.safe_dump({"artifact_schema_version": 99, "cases": []}),
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="artifact_schema_version"):
        build_cases(path)


def test_split_note_overlap_reports_shared_notes():
    shared = [
        _case(sample_id="a", split="development", note_ids=["N1"]),
        _case(sample_id="b", split="validation", note_ids=["N1"]),
        _case(
            sample_id="c",
            split="validation",
            note_ids=["N2"],
            expected=ExpectedRelation(relation="treats", note_ids=["N2"]),
        ),
    ]
    report = split_note_overlap(shared)
    assert report["notes_used"] == 2
    assert report["notes_in_multiple_splits"] == 1
