"""모델이 내놓는 관계 판정과, 채점 전 관찰값·채점 결과의 계약.

원본 `src/verifiable_ai_workflow/schemas/models.py`의 StructuredAnswer 규율을 그대로
따른다. 보류에는 근거를 넣지 않고 판정에는 근거를 요구해서, "잘 모르겠지만 아마
X일 것 같습니다" 식의 물타기가 파싱 단계에서 죽게 한다.

day5 p49 출력 계약(evidence · uncertainty · review_required)의 관계 판정판이다.
"""

from __future__ import annotations

from typing import Any, Literal

from pydantic import Field, model_validator

from .cases import ExpectedLabel
from .injection import InjectionReport, RoutingDecision
from .notes import Contract

EvidenceKind = Literal["test_only", "live_quality"]
ResultStatus = Literal["passed", "failed", "inconclusive"]

# day5 p21 환각 4분류. 실패 원인을 유형으로 갈라야 대응 규칙이 갈린다.
HallucinationKind = Literal["NUMBER", "SOURCE", "OMISSION", "RELATION"]

ABSTAINED_RELATION: ExpectedLabel = "no_relation"


class NoteEvidence(Contract):
    evidence_id: str = Field(min_length=1)
    quote: str = Field(min_length=1)
    note_id: str = Field(min_length=1)


class RelationVerdict(Contract):
    relation: ExpectedLabel
    evidence: list[NoteEvidence] = Field(default_factory=list)
    confidence: float = Field(ge=0.0, le=1.0)
    abstained: bool = False
    abstention_reason: str | None = None
    # 관계 판정에서는 빈 목록을 반환한다.
    tool_requests: list[dict[str, Any]] = Field(default_factory=list, max_length=0)

    @model_validator(mode="after")
    def evidence_matches_abstention(self) -> RelationVerdict:
        if self.abstained:
            if self.relation != ABSTAINED_RELATION or not self.abstention_reason:
                raise ValueError(
                    "보류에는 relation=no_relation과 이유가 필요합니다"
                )
            if self.evidence:
                raise ValueError("보류에는 근거를 넣지 않습니다")
        elif self.relation != ABSTAINED_RELATION and not self.evidence:
            raise ValueError("관계를 인정하는 판정에는 근거가 필요합니다")
        return self


class ModelObservation(Contract):
    """채점하기 전의 원본 관찰값. 모델 응답을 손대지 않고 그대로 남긴다."""

    sample_id: str
    family_id: str
    split: str
    known_note_ids: list[str] = Field(min_length=1)
    raw_output: Any = None
    model_error: str | None = None
    model_call: dict[str, Any] | None = None
    evidence_kind: EvidenceKind


class EvaluationResult(Contract):
    # v2에서 routing·injection이 붙었다. status만으로는 "통과했지만 사람이 봐야 함"과
    # "그냥 통과"를 가를 수 없어서다 (day5 p51).
    artifact_schema_version: Literal[2] = 2
    sample_id: str
    family_id: str
    split: str
    status: ResultStatus
    output: RelationVerdict | None = None
    raw_output: Any = None
    scores: dict[str, float]
    reasons: dict[str, str]
    # 실패한 건에만 붙는다. day5 p21 분류.
    hallucinations: list[HallucinationKind] = Field(default_factory=list)
    # validator 체인이 이 건을 어디로 보냈는지. APPROVED는 없다.
    routing: RoutingDecision = "DRAFT_REVIEW"
    injection: InjectionReport | None = None
    evidence_kind: EvidenceKind
