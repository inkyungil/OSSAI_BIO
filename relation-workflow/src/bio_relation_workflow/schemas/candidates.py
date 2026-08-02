"""후보 개체쌍과 층화·split 배정의 계약."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import Field, model_validator

from .notes import Contract

RelationType = Literal["treats", "has_symptom"]
Split = Literal["development", "validation", "sealed_test"]
Stratum = Literal["reference", "kept_hub", "kept", "dropped_hub", "dropped"]


class CandidatePair(Contract):
    pair_id: str = Field(min_length=1)
    disease: str = Field(min_length=1)
    partner: str = Field(min_length=1)
    partner_label: Literal["약물", "증상"]
    # 동시출현 규칙이 붙인 후보 유형이다. 정답이 아니라 검증 대상이다.
    candidate_relation: RelationType
    support: int = Field(ge=1)
    note_ids: list[str] = Field(min_length=1)
    # 원본은 그래프에 실린 엣지만 참조표와 대조했다. None은 미확인이다.
    in_reference: bool | None = None
    reference_error: bool | None = None
    stratum: Stratum
    split: Split | None = None

    @model_validator(mode="after")
    def support_matches_notes(self) -> CandidatePair:
        if self.support != len(self.note_ids):
            raise ValueError("support는 등장 노트 수와 같아야 합니다")
        if self.note_ids != sorted(set(self.note_ids)):
            raise ValueError("note_ids는 중복 없이 정렬돼야 합니다")
        expected = "약물" if self.candidate_relation == "treats" else "증상"
        if self.partner_label != expected:
            raise ValueError(
                f"{self.candidate_relation}의 상대 개체는 {expected}여야 합니다"
            )
        return self


class CandidateSet(Contract):
    artifact_schema_version: Literal[1] = 1
    corpus_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    min_cooccur: int = Field(ge=1)
    relation_rules: dict[str, str]
    hub_entities: list[str] = Field(default_factory=list)
    candidates: list[CandidatePair] = Field(min_length=1)
    provenance: dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="after")
    def pair_ids_are_unique(self) -> CandidateSet:
        pair_ids = [candidate.pair_id for candidate in self.candidates]
        if len(pair_ids) != len(set(pair_ids)):
            raise ValueError("pair_id는 중복될 수 없습니다")
        keys = [(c.disease, c.partner) for c in self.candidates]
        if len(keys) != len(set(keys)):
            raise ValueError("같은 개체쌍이 두 번 나올 수 없습니다")
        return self

    @property
    def selected(self) -> list[CandidatePair]:
        """split이 배정된 후보만. 라벨링 대상이다."""
        return [candidate for candidate in self.candidates if candidate.split]
