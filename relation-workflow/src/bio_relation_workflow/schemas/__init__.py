"""노트, 후보 개체쌍, 관계 판정과 평가 결과의 계약."""

from .candidates import (
    CandidatePair,
    CandidateSet,
    RelationType,
    Split,
    Stratum,
)
from .cases import (
    ExpectedLabel,
    ExpectedRelation,
    RelationCase,
    RiskLevel,
    SourceMetadata,
)
from .injection import (
    InjectionKind,
    InjectionReport,
    InjectionSignal,
    RoutingDecision,
)
from .notes import ClinicalNote, Contract, Entity, EntityLabel, NoteCorpus
from .verdict import (
    EvaluationResult,
    EvidenceKind,
    HallucinationKind,
    ModelObservation,
    NoteEvidence,
    RelationVerdict,
    ResultStatus,
)

__all__ = [
    "CandidatePair",
    "CandidateSet",
    "ClinicalNote",
    "Contract",
    "Entity",
    "EntityLabel",
    "EvaluationResult",
    "EvidenceKind",
    "ExpectedLabel",
    "ExpectedRelation",
    "HallucinationKind",
    "InjectionKind",
    "InjectionReport",
    "InjectionSignal",
    "ModelObservation",
    "NoteCorpus",
    "NoteEvidence",
    "RelationCase",
    "RelationType",
    "RelationVerdict",
    "ResultStatus",
    "RiskLevel",
    "RoutingDecision",
    "SourceMetadata",
    "Split",
    "Stratum",
]
