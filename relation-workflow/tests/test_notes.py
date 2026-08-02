"""노트 코퍼스 복원과 개체 탐지 계약."""

from __future__ import annotations

import json
from collections import Counter

import pytest
from pydantic import ValidationError

from bio_relation_workflow.preprocessing import (
    extract_embedded_data,
    find_entities,
    nested_entities,
)
from bio_relation_workflow.schemas import ClinicalNote, Entity, NoteCorpus

SHA = "0" * 64


def test_embedded_data_requires_const_block():
    with pytest.raises(ValueError, match="const DATA"):
        extract_embedded_data("<html><body>DATA 없음</body></html>")


def test_embedded_data_reads_inline_object():
    html = '<script>\nconst DATA = {\n  "a": 1\n};\n</script>'
    assert extract_embedded_data(html) == {"a": 1}


def test_find_entities_prefers_longest_match():
    # "위"가 "위염"을 삼키면 질병 개체를 놓친다 (day2 규칙 NER 최장 일치).
    assert find_entities("위염 관리 필요", ["위", "위염"]) == ["위염"]


def test_find_entities_returns_sorted_unique():
    text = "폐렴 환자가 발열을 호소했고 폐렴 소견이 있다"
    assert find_entities(text, ["폐렴", "발열"]) == ["발열", "폐렴"]


def test_find_entities_ignores_absent():
    assert find_entities("두통만 있다", ["폐렴", "발열"]) == []


def test_nested_entities_reports_substring_pairs():
    assert nested_entities(["위", "위염", "폐렴"]) == [("위", "위염")]
    assert nested_entities(["위염", "폐렴"]) == []


def test_note_rejects_unsorted_entities():
    with pytest.raises(ValidationError, match="정렬"):
        ClinicalNote(note_id="N1", text="본문", entities=["폐렴", "발열"])


def test_note_rejects_duplicate_entities():
    with pytest.raises(ValidationError, match="정렬"):
        ClinicalNote(note_id="N1", text="본문", entities=["폐렴", "폐렴"])


def _corpus(**overrides):
    payload = {
        "source_file": "x.html",
        "source_sha256": SHA,
        "notes": [ClinicalNote(note_id="N1", text="폐렴", entities=["폐렴"])],
        "entities": [Entity(entity_id="폐렴", label="질병")],
    }
    payload.update(overrides)
    return NoteCorpus(**payload)


def test_corpus_rejects_duplicate_note_ids():
    note = ClinicalNote(note_id="N1", text="폐렴", entities=["폐렴"])
    with pytest.raises(ValidationError, match="note_id"):
        _corpus(notes=[note, note])


def test_corpus_rejects_entity_outside_dictionary():
    with pytest.raises(ValidationError, match="사전에 없는 개체"):
        _corpus(notes=[ClinicalNote(note_id="N1", text="발열", entities=["발열"])])


def test_corpus_rejects_unknown_entity_label():
    with pytest.raises(ValidationError):
        Entity(entity_id="폐렴", label="검사")


# --- 생성된 실제 코퍼스 ---


def _generated_notes(corpus):
    """주입 평가용으로 직접 쓴 노트를 뺀, 프로토타입에서 복원한 노트."""
    injected = set(corpus.provenance.get("injection_notes", []))
    return [note for note in corpus.notes if note.note_id not in injected]


def test_corpus_counts(corpus):
    assert len(_generated_notes(corpus)) == 108
    assert len(corpus.entities) == 30
    assert Counter(e.label for e in corpus.entities) == {
        "질병": 12,
        "약물": 10,
        "증상": 8,
    }


def test_corpus_note_ids_unique_and_texts_distinct_per_id(corpus):
    note_ids = [note.note_id for note in corpus.notes]
    assert len(note_ids) == len(set(note_ids))


def test_every_note_has_at_least_two_entities(corpus):
    # 개체쌍 후보를 만들려면 노트마다 개체가 둘 이상이어야 한다.
    assert all(len(note.entities) >= 2 for note in corpus.notes)


def test_corpus_records_source_shortfall(corpus):
    # HTML에 실린 노트는 원본의 일부다. 한계를 기계가 읽을 수 있게 남긴다.
    assert corpus.provenance["notes_in_source"] == 150
    assert corpus.provenance["notes_recovered"] == 108


def test_injection_notes_are_marked(corpus):
    # 주입 노트는 코퍼스에 들어가되 후보 재계산에서 빠져야 한다.
    injected = corpus.provenance.get("injection_notes", [])
    if not injected:
        pytest.skip("먼저 merge_injection_cases.py를 실행하세요")
    assert set(injected) <= {note.note_id for note in corpus.notes}
    assert len(corpus.notes) == 108 + len(injected)


def test_corpus_roundtrip(corpus, tmp_path):
    from bio_relation_workflow.preprocessing import load_corpus, write_corpus

    target = tmp_path / "corpus.json"
    write_corpus(corpus, target)
    assert load_corpus(target) == corpus
    assert json.loads(target.read_text(encoding="utf-8"))["artifact_schema_version"] == 1
