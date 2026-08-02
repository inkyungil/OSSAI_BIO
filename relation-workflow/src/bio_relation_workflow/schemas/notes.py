"""임상 노트 코퍼스와 개체 사전의 계약.

원본 `src/verifiable_ai_workflow/schemas/models.py`의 Contract·PreparedDocument 규약을
따른다. 파일로 저장하거나 함수 사이에 전달하는 값만 담는다.
"""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

EntityLabel = Literal["질병", "약물", "증상"]


class Contract(BaseModel):
    model_config = ConfigDict(extra="forbid")


class Entity(Contract):
    entity_id: str = Field(min_length=1)
    label: EntityLabel


class ClinicalNote(Contract):
    note_id: str = Field(min_length=1)
    text: str = Field(min_length=1)
    # 최장 일치로 찾은 등장 개체. 정렬·중복 제거된 entity_id 목록이다.
    entities: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def entities_are_sorted_and_unique(self) -> ClinicalNote:
        if self.entities != sorted(set(self.entities)):
            raise ValueError("entities는 중복 없이 정렬돼야 합니다")
        return self


class NoteCorpus(Contract):
    artifact_schema_version: Literal[1] = 1
    source_file: str = Field(min_length=1)
    source_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    notes: list[ClinicalNote] = Field(min_length=1)
    entities: list[Entity] = Field(min_length=1)
    # 원본 DATA의 meta·settings·summary를 그대로 보존해 출처를 추적한다.
    provenance: dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="after")
    def identifiers_are_unique(self) -> NoteCorpus:
        note_ids = [note.note_id for note in self.notes]
        if len(note_ids) != len(set(note_ids)):
            raise ValueError("note_id는 중복될 수 없습니다")
        entity_ids = [entity.entity_id for entity in self.entities]
        if len(entity_ids) != len(set(entity_ids)):
            raise ValueError("entity_id는 중복될 수 없습니다")
        known = set(entity_ids)
        for note in self.notes:
            unknown = set(note.entities) - known
            if unknown:
                raise ValueError(f"사전에 없는 개체입니다: {sorted(unknown)}")
        return self
