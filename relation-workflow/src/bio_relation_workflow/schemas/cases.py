"""평가 케이스와 정답 계약.

원본 `src/verifiable_ai_workflow/schemas/models.py`의 EvaluationCase·ExpectedAnswer
규약을 관계 판정으로 옮긴 것이다. 정답의 보류 규칙(보류면 근거를 비운다)을 그대로 지킨다.
"""

from __future__ import annotations

from typing import Literal

from pydantic import Field, model_validator

from .candidates import RelationType, Split, Stratum
from .notes import Contract

# 정답 라벨. 후보 유형(treats/has_symptom)이 맞는지, 아니면 관계가 아닌지를 가른다.
ExpectedLabel = Literal["treats", "has_symptom", "no_relation"]
RiskLevel = Literal["low", "medium", "high"]


class SourceMetadata(Contract):
    title: str = Field(min_length=1)
    license: str = Field(min_length=1)
    revision: str = Field(min_length=1)


class ExpectedRelation(Contract):
    relation: ExpectedLabel
    # 같은 판정을 여러 노트가 뒷받침하면 하나만 인용해도 되도록 모두 적는다.
    note_ids: list[str] = Field(default_factory=list)
    abstained: bool = False

    @model_validator(mode="after")
    def notes_match_abstention(self) -> ExpectedRelation:
        if self.abstained:
            if self.relation != "no_relation" or self.note_ids:
                raise ValueError(
                    "보류 기대값은 relation=no_relation과 빈 note_ids가 필요합니다"
                )
        elif self.relation != "no_relation" and not self.note_ids:
            raise ValueError("관계를 인정하는 기대값에는 근거 노트가 필요합니다")
        if self.note_ids != sorted(set(self.note_ids)):
            raise ValueError("note_ids는 중복 없이 정렬돼야 합니다")
        return self


class RelationCase(Contract):
    artifact_schema_version: Literal[1] = 1
    sample_id: str = Field(min_length=1)
    # 같은 질병에서 나온 후보를 묶는다. split 사이 노트 중복을 측정할 때 쓴다.
    family_id: str = Field(min_length=1)
    pair_id: str = Field(min_length=1)
    disease: str = Field(min_length=1)
    partner: str = Field(min_length=1)
    partner_label: Literal["약물", "증상"]
    candidate_relation: RelationType
    support: int = Field(ge=1)
    note_ids: list[str] = Field(min_length=1)
    split: Split
    stratum: Stratum
    risk_level: RiskLevel
    source: SourceMetadata
    expected: ExpectedRelation
    in_reference: bool | None = None
    reference_error: bool | None = None
    tags: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def expected_notes_come_from_candidate(self) -> RelationCase:
        unknown = set(self.expected.note_ids) - set(self.note_ids)
        if unknown:
            raise ValueError(
                f"정답 근거가 후보의 등장 노트 밖입니다: {sorted(unknown)}"
            )
        return self
