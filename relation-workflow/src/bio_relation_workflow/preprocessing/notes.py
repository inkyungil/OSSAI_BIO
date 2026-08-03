"""프로토타입 HTML의 사전계산 JSON에서 임상 노트 코퍼스를 복원한다.

`day6/relation-explorer.html`은 day3 관계추출 실습 결과를 `const DATA`로 품고 있다.
노트 전문은 각 엣지의 evidence에 흩어져 있으므로 note_id 기준으로 다시 모은다.

개체 탐지는 day2의 규칙 NER 규율을 따라 최장 일치를 쓴다. 짧은 개체가 긴 개체를 삼켜
경계를 망가뜨리는 것을 막는다.
"""

from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path
from typing import Any

from ..schemas import ClinicalNote, Entity, NoteCorpus

_DATA_PATTERN = re.compile(r"const\s+DATA\s*=\s*(\{.*?\n\})\s*;", re.DOTALL)


def extract_embedded_data(html_text: str) -> dict[str, Any]:
    """HTML에 인라인된 `const DATA` 객체를 dict로 읽는다."""
    match = _DATA_PATTERN.search(html_text)
    if match is None:
        raise ValueError("HTML에서 `const DATA` 블록을 찾지 못했습니다")
    return json.loads(match.group(1))


def nested_entities(entity_ids: list[str]) -> list[tuple[str, str]]:
    """다른 개체의 부분 문자열인 개체 쌍을 (짧은 것, 긴 것)으로 돌려준다.

    비어 있지 않다면 최장 일치가 실제로 필요하다는 뜻이다.
    """
    return [
        (short, long)
        for short in entity_ids
        for long in entity_ids
        if short != long and short in long
    ]


def find_entities(text: str, entity_ids: list[str]) -> list[str]:
    """최장 일치로 문장에 등장한 개체를 찾는다."""
    masked = [False] * len(text)
    found: set[str] = set()
    for entity_id in sorted(entity_ids, key=len, reverse=True):
        start = 0
        while (index := text.find(entity_id, start)) >= 0:
            end = index + len(entity_id)
            if not any(masked[index:end]):
                found.add(entity_id)
                for position in range(index, end):
                    masked[position] = True
            start = index + 1
    return sorted(found)


def build_corpus(html_path: str | Path) -> NoteCorpus:
    source = Path(html_path)
    html_text = source.read_text(encoding="utf-8")
    data = extract_embedded_data(html_text)

    entities: dict[str, str] = {}
    note_texts: dict[str, str] = {}
    for graph in data["graphs"].values():
        for node in graph["nodes"]:
            entities.setdefault(node["id"], node["label"])
        for edge in graph["edges"]:
            for evidence in edge.get("evidence", []):
                note_id = evidence["note_id"]
                text = evidence["text"]
                previous = note_texts.setdefault(note_id, text)
                if previous != text:
                    raise ValueError(
                        f"같은 note_id에 다른 본문이 있습니다: {note_id}"
                    )

    entity_ids = sorted(entities)
    notes = [
        ClinicalNote(
            note_id=note_id,
            text=note_texts[note_id],
            entities=find_entities(note_texts[note_id], entity_ids),
        )
        for note_id in sorted(note_texts)
    ]

    return NoteCorpus(
        source_file=source.name,
        source_sha256=hashlib.sha256(source.read_bytes()).hexdigest(),
        notes=notes,
        entities=[
            Entity(entity_id=entity_id, label=entities[entity_id])
            for entity_id in entity_ids
        ],
        provenance={
            "meta": data["meta"],
            "settings": data["settings"],
            "summary": data["summary"],
            # HTML에 실린 노트는 원본 150건의 일부다. 결과 보고 시 명시한다.
            "notes_in_source": data["meta"]["total_notes"],
            "notes_recovered": len(notes),
            "nested_entities": nested_entities(entity_ids),
        },
    )


def write_corpus(corpus: NoteCorpus, path: str | Path) -> None:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(
        corpus.model_dump_json(indent=2) + "\n",
        encoding="utf-8",
    )


def load_corpus(path: str | Path) -> NoteCorpus:
    return NoteCorpus.model_validate_json(Path(path).read_text(encoding="utf-8"))
